from __future__ import annotations

from dataclasses import dataclass

from simulator.models import TelemetryFrame

NOMINAL_FLOW = 95.0
RECIRCULATION_FLOW = 20.0
LEAKAGE_FLOW = 1.0
NOMINAL_PRESSURE = 3.2
NOMINAL_CONCENTRATION = 2.0
NOMINAL_POWER = 3.0
IDLE_POWER = 0.08
BASE_CONDUCTIVITY = 450.0
CONDUCTIVITY_K = 25.0
MIN_FLOW_FOR_DOSING = 5.0


@dataclass
class SensorPrediction:
    tag: str
    predicted: float
    observed: float
    expected_range: float  # denominator for residual normalisation


def predict(frame: TelemetryFrame) -> list[SensorPrediction]:
    c = frame.command_state
    mode = frame.operating_mode

    # FT-101: flow rate
    if not (c.valve_open or c.bypass_open):
        ft101_pred = LEAKAGE_FLOW
    elif c.pump_commanded:
        ft101_pred = NOMINAL_FLOW if mode == "normal" else RECIRCULATION_FLOW
    else:
        ft101_pred = 0.0

    # PT-101: downstream pressure
    pt101_pred = NOMINAL_PRESSURE if c.pump_commanded else 0.0

    # AT-101: chemical concentration
    # When dosing active with adequate flow, reading should hold near nominal.
    # Without dosing, the reading drifts toward a low baseline.
    flow = frame.primary.flow_rate
    if c.dosing_active and flow >= MIN_FLOW_FOR_DOSING:
        at101_pred = NOMINAL_CONCENTRATION
    else:
        at101_pred = 0.3

    # PM-101: pump power draw
    pm101_pred = NOMINAL_POWER if c.pump_commanded else IDLE_POWER

    # CT-101: downstream conductivity — correlated with predicted concentration
    ct101_pred = BASE_CONDUCTIVITY + CONDUCTIVITY_K * at101_pred

    return [
        SensorPrediction("FT-101", ft101_pred, frame.primary.flow_rate, NOMINAL_FLOW),
        SensorPrediction("PT-101", pt101_pred, frame.primary.downstream_pressure, NOMINAL_PRESSURE),
        SensorPrediction("AT-101", at101_pred, frame.primary.chemical_concentration, NOMINAL_CONCENTRATION),
        SensorPrediction("PM-101", pm101_pred, frame.secondary.pump_power_draw, NOMINAL_POWER),
        SensorPrediction("CT-101", ct101_pred, frame.secondary.downstream_conductivity, 150.0),
    ]
