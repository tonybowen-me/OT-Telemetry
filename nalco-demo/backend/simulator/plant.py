from __future__ import annotations

import math
from collections import deque
from datetime import datetime, timezone

from .anomalies import AnomalyState, AnomalyType
from .models import CommandState, PrimaryReadings, SecondaryReadings, TelemetryFrame
from .sensors import noisy

# ---------------------------------------------------------------------------
# Nominal operating constants
# ---------------------------------------------------------------------------
NOMINAL_FLOW = 95.0          # L/min  — full-flow operating point
RECIRCULATION_FLOW = 20.0    # L/min  — low-flow recirculation mode
LEAKAGE_FLOW = 1.0           # L/min  — closed-valve leakage
NOMINAL_PRESSURE = 3.2       # bar
NOMINAL_LEVEL = 65.0         # %
NOMINAL_CONCENTRATION = 2.0  # mg/L   — chlorine residual setpoint
NOMINAL_POWER = 3.0          # kW     — P-101 at full load
IDLE_POWER = 0.08            # kW     — standby draw when pump is off
BASE_CONDUCTIVITY = 450.0    # µS/cm  — base water conductivity
CONDUCTIVITY_K = 25.0        # µS/cm per mg/L of chlorine residual

# First-order lag coefficients (per tick)
PRESSURE_LAG = 0.3
FLOW_LAG = 0.4
CONCENTRATION_LAG = 0.05     # slow — residence time in tank

CONDUCTIVITY_LAG_WINDOW = 5  # ticks — residence-time approximation for CT-101
SLOW_DRIFT_RATE = 0.02       # mg/L per tick injected onto AT-101


class WaterTreatmentPlant:
    """
    Simulates a chemical dosing water treatment loop.

    Physical topology
    -----------------
    P-101  Main centrifugal intake pump
    V-101  Main isolation valve
    V-102  Bypass valve
    P-102  Chemical dosing metering pump (chlorine / anti-scale)
    T-101  Treatment / buffer tank

    Instruments
    -----------
    FT-101  Flow transmitter, downstream of P-101        (primary)
    LT-101  Tank level transmitter on T-101              (primary)
    PT-101  Downstream pressure transmitter              (primary)
    AT-101  Chlorine residual analyser                   (primary)
    PM-101  Power meter on P-101                         (secondary)
    CT-101  Downstream conductivity sensor               (secondary)
    """

    def __init__(self) -> None:
        # True physical state — internal, never spoofed
        self._flow = NOMINAL_FLOW
        self._pressure = NOMINAL_PRESSURE
        self._level = NOMINAL_LEVEL
        self._concentration = NOMINAL_CONCENTRATION
        self._power = NOMINAL_POWER

        # Command / control state
        self._pump_commanded = True
        self._valve_open = True
        self._bypass_open = False
        self._dosing_active = True
        self._mode: str = "normal"

        # Rolling concentration history drives conductivity lag (CT-101)
        self._concentration_history: deque[float] = deque(
            [NOMINAL_CONCENTRATION] * CONDUCTIVITY_LAG_WINDOW,
            maxlen=CONDUCTIVITY_LAG_WINDOW,
        )

        self._anomaly = AnomalyState()
        self._tick = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        if mode not in ("normal", "recirculation"):
            raise ValueError(f"Unknown mode: {mode!r}")
        self._mode = mode

    def inject_anomaly(self, anomaly_type: str) -> None:
        self.clear_anomaly()
        self._anomaly.type = AnomalyType(anomaly_type)
        # Sensor spoof precondition: attacker closes V-101 to break real flow,
        # then falsifies FT-101 to hide it
        if self._anomaly.type == AnomalyType.SENSOR_SPOOF:
            self._valve_open = False

    def clear_anomaly(self) -> None:
        if self._anomaly.type == AnomalyType.SENSOR_SPOOF:
            self._valve_open = True
        self._anomaly.reset()

    def tick(self) -> TelemetryFrame:
        self._tick += 1
        self._anomaly.ticks_active += 1
        self._update_physics()
        frame = self._build_frame()
        return self._apply_anomaly(frame)

    # ------------------------------------------------------------------
    # Physics update (true plant state, one tick forward)
    # ------------------------------------------------------------------

    def _update_physics(self) -> None:
        # Pump failure: commanded on but mechanically not running
        pump_actually_on = (
            self._pump_commanded
            and self._anomaly.type != AnomalyType.PUMP_FAILURE
        )

        # Flow (FT-101 truth)
        if pump_actually_on and self._valve_open:
            flow_target = NOMINAL_FLOW if self._mode == "normal" else RECIRCULATION_FLOW
        elif pump_actually_on and self._bypass_open:
            flow_target = RECIRCULATION_FLOW
        elif not self._valve_open and not self._bypass_open:
            flow_target = LEAKAGE_FLOW
        else:
            flow_target = 0.0
        self._flow += FLOW_LAG * (flow_target - self._flow)

        # Pressure (PT-101 truth)
        pressure_target = NOMINAL_PRESSURE if pump_actually_on else 0.0
        self._pressure += PRESSURE_LAG * (pressure_target - self._pressure)
        self._pressure = max(0.0, self._pressure)

        # Tank level (LT-101 truth) — slow sinusoidal oscillation around setpoint.
        # In a real plant this would be a mass balance; for demo the slow wave
        # makes level look realistic without dominating the interesting signals.
        self._level = NOMINAL_LEVEL + 3.0 * math.sin(self._tick * 2 * math.pi / 120)

        # Chemical concentration (AT-101 truth)
        flow_sufficient = self._flow > 5.0 or self._mode == "recirculation"
        c_target = NOMINAL_CONCENTRATION if (self._dosing_active and flow_sufficient) else 0.0
        self._concentration += CONCENTRATION_LAG * (c_target - self._concentration)
        self._concentration = max(0.0, self._concentration)
        self._concentration_history.append(self._concentration)

        # Power draw (PM-101 truth)
        if pump_actually_on:
            # Power proportional to hydraulic load (flow × pressure / efficiency)
            self._power = (
                (self._flow / NOMINAL_FLOW)
                * (max(0.1, self._pressure) / NOMINAL_PRESSURE)
                * NOMINAL_POWER
            )
        else:
            self._power = IDLE_POWER

    # ------------------------------------------------------------------
    # Frame construction (reads from true state + noise)
    # ------------------------------------------------------------------

    def _build_frame(self) -> TelemetryFrame:
        lagged_conc = sum(self._concentration_history) / len(self._concentration_history)
        conductivity = BASE_CONDUCTIVITY + CONDUCTIVITY_K * lagged_conc

        return TelemetryFrame(
            timestamp=datetime.now(timezone.utc),
            tick_number=self._tick,
            operating_mode=self._mode,  # type: ignore[arg-type]
            command_state=CommandState(
                pump_commanded=self._pump_commanded,
                valve_open=self._valve_open,
                bypass_open=self._bypass_open,
                dosing_active=self._dosing_active,
                mode=self._mode,  # type: ignore[arg-type]
            ),
            primary=PrimaryReadings(
                flow_rate=round(max(0.0, noisy(self._flow, "flow_rate")), 2),
                tank_level=round(noisy(self._level, "tank_level"), 2),
                downstream_pressure=round(max(0.0, noisy(self._pressure, "downstream_pressure")), 3),
                chemical_concentration=round(max(0.0, noisy(self._concentration, "chemical_concentration")), 3),
            ),
            secondary=SecondaryReadings(
                pump_power_draw=round(max(0.0, noisy(self._power, "pump_power_draw")), 3),
                downstream_conductivity=round(max(0.0, noisy(conductivity, "downstream_conductivity")), 1),
            ),
            active_anomaly=self._anomaly.type.value if self._anomaly.is_active else None,
        )

    # ------------------------------------------------------------------
    # Anomaly injection (corrupts reported readings, not physics truth)
    # ------------------------------------------------------------------

    def _apply_anomaly(self, frame: TelemetryFrame) -> TelemetryFrame:
        match self._anomaly.type:
            case AnomalyType.SENSOR_SPOOF:
                # FT-101 falsified to report nominal flow while V-101 is closed.
                # Real flow is ~leakage only — Layer 1 flow continuity rule fires.
                return frame.model_copy(update={
                    "primary": frame.primary.model_copy(update={
                        "flow_rate": round(max(0.0, noisy(NOMINAL_FLOW, "flow_rate")), 2)
                    })
                })

            case AnomalyType.SLOW_DRIFT:
                # AT-101 reading accumulates an upward offset each tick.
                # Physics concentration is normal — only the reported value drifts.
                # Layer 2 detects via sustained residual; Layer 1 won't trip.
                self._anomaly.drift_accumulator += SLOW_DRIFT_RATE
                return frame.model_copy(update={
                    "primary": frame.primary.model_copy(update={
                        "chemical_concentration": round(
                            frame.primary.chemical_concentration + self._anomaly.drift_accumulator,
                            3,
                        )
                    })
                })

            case AnomalyType.REPLAY_ATTACK:
                # First tick: capture the clean frame as the frozen snapshot.
                if self._anomaly.replay_snapshot is None:
                    self._anomaly.replay_snapshot = frame
                    return frame
                # Subsequent ticks: primary + secondary readings are frozen to the
                # snapshot. Tick number and timestamp still advance, so Layer 2
                # detects that concentration isn't rising despite active dosing.
                return frame.model_copy(update={
                    "primary": self._anomaly.replay_snapshot.primary,
                    "secondary": self._anomaly.replay_snapshot.secondary,
                })

            case _:
                # PUMP_FAILURE: no reading override — physics is the anomaly.
                # NONE: pass through.
                return frame
