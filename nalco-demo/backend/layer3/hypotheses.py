from __future__ import annotations

from collections import deque

from simulator.models import TelemetryFrame
from .models import HypothesisResult

NOMINAL_FLOW = 95.0
RECIRCULATION_FLOW = 20.0
LEAKAGE_THRESHOLD = 2.5
NOMINAL_PRESSURE = 3.2
NOMINAL_CONCENTRATION = 2.0
NOMINAL_POWER = 3.0
IDLE_POWER = 0.08
MIN_FLOW_FOR_DOSING = 5.0


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def score_sensor_spoof(frame: TelemetryFrame, history: deque) -> HypothesisResult:
    c = frame.command_state
    flow = frame.primary.flow_rate
    power = frame.secondary.pump_power_draw
    conc = frame.primary.chemical_concentration
    evidence: list[str] = []
    scores: list[float] = []
    weights: list[float] = []

    # 1. Valves closed but flow elevated — the smoking gun
    both_closed = not c.valve_open and not c.bypass_open
    if both_closed:
        if flow > LEAKAGE_THRESHOLD:
            evidence.append(
                f"FT-101 = {flow:.1f} L/min with both valves closed — "
                f"physically impossible without sensor falsification"
            )
            scores.append(1.0)
        else:
            evidence.append(f"Valves closed, FT-101 = {flow:.1f} L/min (within leakage bounds)")
            scores.append(0.1)
    else:
        evidence.append("At least one valve open — direct valve contradiction absent")
        scores.append(0.05)
    weights.append(0.55)

    # 2. PM-101 inconsistent with reported flow
    if flow > LEAKAGE_THRESHOLD * 3 and power < IDLE_POWER * 2:
        evidence.append(
            f"PM-101 = {power:.3f} kW at idle despite FT-101 = {flow:.1f} L/min — "
            f"no power source for reported flow"
        )
        scores.append(0.9)
    elif abs(power - (NOMINAL_POWER if flow > 50 else IDLE_POWER)) / NOMINAL_POWER > 0.5:
        evidence.append(f"PM-101 = {power:.3f} kW inconsistent with FT-101 = {flow:.1f} L/min")
        scores.append(0.5)
    else:
        evidence.append(f"PM-101 = {power:.3f} kW roughly consistent with reported flow")
        scores.append(0.1)
    weights.append(0.30)

    # 3. Concentration near nominal (spoof typically targets flow only)
    if abs(conc - NOMINAL_CONCENTRATION) < 0.3:
        evidence.append(f"AT-101 = {conc:.3f} mg/L near nominal — concentration plausible, spoof isolated to FT-101")
        scores.append(0.6)
    else:
        evidence.append(f"AT-101 = {conc:.3f} mg/L deviates from nominal — may indicate secondary anomaly")
        scores.append(0.3)
    weights.append(0.15)

    confidence = _clamp(sum(s * w for s, w in zip(scores, weights)))
    return HypothesisResult(
        name="SENSOR_SPOOF", label="Sensor Spoof (FT-101)",
        confidence=round(confidence, 3), evidence=evidence,
    )


def score_pump_failure(frame: TelemetryFrame, history: deque) -> HypothesisResult:
    c = frame.command_state
    if not c.pump_commanded:
        return HypothesisResult(
            name="PUMP_FAILURE", label="Pump Mechanical Failure",
            confidence=0.0,
            evidence=["Pump P-101 is commanded OFF — pump failure hypothesis does not apply"],
        )

    flow = frame.primary.flow_rate
    power = frame.secondary.pump_power_draw
    pressure = frame.primary.downstream_pressure
    expected_flow = NOMINAL_FLOW if frame.operating_mode == "normal" else RECIRCULATION_FLOW
    evidence: list[str] = ["Pump P-101 is commanded ON"]
    scores: list[float] = []
    weights: list[float] = []

    # 1. PM-101 at idle despite command
    if power < IDLE_POWER * 2:
        evidence.append(
            f"PM-101 = {power:.3f} kW — standby draw only, expected ~{NOMINAL_POWER} kW for active pumping"
        )
        scores.append(1.0)
    elif power < NOMINAL_POWER * 0.5:
        evidence.append(f"PM-101 = {power:.3f} kW — below normal pumping load")
        scores.append(0.5)
    else:
        evidence.append(f"PM-101 = {power:.3f} kW — consistent with active pumping")
        scores.append(0.0)
    weights.append(0.45)

    # 2. FT-101 low/decaying
    if flow < MIN_FLOW_FOR_DOSING:
        evidence.append(f"FT-101 = {flow:.1f} L/min — near zero, pump not moving fluid")
        scores.append(1.0)
    elif flow < expected_flow * 0.5:
        evidence.append(f"FT-101 = {flow:.1f} L/min — significantly below nominal {expected_flow:.0f} L/min")
        scores.append(0.6)
    else:
        evidence.append(f"FT-101 = {flow:.1f} L/min — within acceptable range")
        scores.append(0.0)
    weights.append(0.35)

    # 3. Pressure decaying
    if pressure < NOMINAL_PRESSURE * 0.5:
        evidence.append(f"PT-101 = {pressure:.3f} bar — pressure collapsed, no pumping force")
        scores.append(0.9)
    elif pressure < NOMINAL_PRESSURE * 0.8:
        evidence.append(f"PT-101 = {pressure:.3f} bar — pressure below nominal and degrading")
        scores.append(0.5)
    else:
        evidence.append(f"PT-101 = {pressure:.3f} bar — pressure nominally maintained")
        scores.append(0.0)
    weights.append(0.20)

    confidence = _clamp(sum(s * w for s, w in zip(scores, weights)))
    return HypothesisResult(
        name="PUMP_FAILURE", label="Pump Mechanical Failure",
        confidence=round(confidence, 3), evidence=evidence,
    )


def score_slow_drift(frame: TelemetryFrame, history: deque) -> HypothesisResult:
    c = frame.command_state
    flow = frame.primary.flow_rate
    conc = frame.primary.chemical_concentration
    evidence: list[str] = []
    scores: list[float] = []
    weights: list[float] = []

    # 1. AT-101 deviation from nominal
    deviation = abs(conc - NOMINAL_CONCENTRATION) / NOMINAL_CONCENTRATION
    if deviation > 0.3:
        evidence.append(
            f"AT-101 = {conc:.3f} mg/L — {deviation*100:.0f}% deviation from "
            f"nominal {NOMINAL_CONCENTRATION} mg/L"
        )
        scores.append(_clamp(deviation * 1.5))
    elif deviation > 0.1:
        evidence.append(f"AT-101 = {conc:.3f} mg/L — modest deviation from nominal")
        scores.append(0.3)
    else:
        evidence.append(f"AT-101 = {conc:.3f} mg/L — near nominal, drift minor")
        scores.append(0.0)
    weights.append(0.30)

    # 2. Monotonic trend across history
    if len(history) >= 5:
        conc_vals = [f.primary.chemical_concentration for f in history]
        diffs = [conc_vals[i + 1] - conc_vals[i] for i in range(len(conc_vals) - 1)]
        pos = sum(1 for d in diffs if d > 0.01)
        neg = sum(1 for d in diffs if d < -0.01)
        total = len(diffs)
        mono_ratio = max(pos, neg) / total if total > 0 else 0
        direction = "upward" if pos > neg else "downward"
        if mono_ratio > 0.7:
            evidence.append(
                f"AT-101 trending consistently {direction} across {total} ticks "
                f"({mono_ratio*100:.0f}% monotonic) — characteristic of injected drift"
            )
            scores.append(mono_ratio)
        elif mono_ratio > 0.5:
            evidence.append(f"AT-101 shows {direction} tendency with some reversal")
            scores.append(0.4)
        else:
            evidence.append("AT-101 shows no consistent directional trend in history")
            scores.append(0.0)
    else:
        evidence.append("Insufficient history for trend analysis")
        scores.append(0.1)
    weights.append(0.40)

    # 3. Dosing active and flow adequate — drift is unexplained by command state
    if c.dosing_active and flow >= MIN_FLOW_FOR_DOSING:
        evidence.append(
            f"P-102 dosing active with {flow:.1f} L/min carrier flow — "
            f"drift has no commanded explanation"
        )
        scores.append(0.9)
    elif not c.dosing_active:
        evidence.append("Dosing is off — concentration change may have a commanded explanation")
        scores.append(0.1)
    else:
        evidence.append(f"Dosing active but flow = {flow:.1f} L/min — DOSING_FAULT also possible")
        scores.append(0.4)
    weights.append(0.20)

    # 4. Per-tick changes are small (distinguishes drift from step-change spoof)
    if len(history) >= 2:
        hist_list = list(history)
        recent_delta = abs(
            hist_list[-1].primary.chemical_concentration
            - hist_list[-2].primary.chemical_concentration
        )
        if recent_delta < 0.10:
            evidence.append(
                f"Per-tick Δ = {recent_delta:.3f} mg/L — "
                f"consistent with slow drift, not step-change injection"
            )
            scores.append(0.8)
        else:
            evidence.append(f"Per-tick Δ = {recent_delta:.3f} mg/L — larger than typical drift step")
            scores.append(0.2)
    else:
        evidence.append("Insufficient history for per-tick delta check")
        scores.append(0.5)
    weights.append(0.10)

    confidence = _clamp(sum(s * w for s, w in zip(scores, weights)))
    return HypothesisResult(
        name="SLOW_DRIFT", label="Slow Concentration Drift Attack",
        confidence=round(confidence, 3), evidence=evidence,
    )


def score_replay_attack(frame: TelemetryFrame, history: deque) -> HypothesisResult:
    if len(history) < 6:
        return HypothesisResult(
            name="REPLAY_ATTACK", label="Sensor Replay Attack",
            confidence=0.0, evidence=["Insufficient history for replay detection (need ≥6 ticks)"],
        )

    c = frame.command_state
    hist_list = list(history)
    window = hist_list[-10:]
    evidence: list[str] = []
    scores: list[float] = []
    weights: list[float] = []

    # 1. Primary readings near-identical across the window
    flow_var = max(f.primary.flow_rate for f in window) - min(f.primary.flow_rate for f in window)
    conc_var = (
        max(f.primary.chemical_concentration for f in window)
        - min(f.primary.chemical_concentration for f in window)
    )
    pressure_var = (
        max(f.primary.downstream_pressure for f in window)
        - min(f.primary.downstream_pressure for f in window)
    )
    frozen = sum([flow_var < 1.0, conc_var < 0.02, pressure_var < 0.02])
    if frozen >= 2:
        evidence.append(
            f"Multiple sensors frozen over {len(window)} ticks — "
            f"flow Δ={flow_var:.2f}, conc Δ={conc_var:.3f}, pressure Δ={pressure_var:.3f}"
        )
        scores.append(0.9)
    elif frozen == 1:
        evidence.append(f"One sensor appears static — flow Δ={flow_var:.2f}, conc Δ={conc_var:.3f}")
        scores.append(0.45)
    else:
        evidence.append(f"Sensors show natural variation — flow Δ={flow_var:.2f}, conc Δ={conc_var:.3f}")
        scores.append(0.0)
    weights.append(0.50)

    # 2. Concentration unresponsive to active dosing
    if c.dosing_active and frame.primary.flow_rate >= MIN_FLOW_FOR_DOSING:
        if conc_var < 0.05:
            evidence.append(
                f"P-102 dosing active with adequate flow, but AT-101 unchanged "
                f"across {len(window)} ticks — readings are stale"
            )
            scores.append(0.9)
        else:
            evidence.append(f"AT-101 responding to dosing — concentration varies (Δ={conc_var:.3f} mg/L)")
            scores.append(0.0)
    else:
        evidence.append("Dosing inactive or insufficient flow — concentration freeze has a commanded explanation")
        scores.append(0.15)
    weights.append(0.35)

    # 3. Tick counter advancing normally while readings are frozen
    ticks = [f.tick_number for f in hist_list[-5:]]
    tick_diffs = [ticks[i + 1] - ticks[i] for i in range(len(ticks) - 1)]
    if all(d == 1 for d in tick_diffs):
        evidence.append("Tick counter advancing normally while sensor readings appear frozen")
        scores.append(0.8)
    else:
        evidence.append("Tick counter irregular")
        scores.append(0.2)
    weights.append(0.15)

    confidence = _clamp(sum(s * w for s, w in zip(scores, weights)))
    return HypothesisResult(
        name="REPLAY_ATTACK", label="Sensor Replay Attack",
        confidence=round(confidence, 3), evidence=evidence,
    )


def score_dosing_fault(frame: TelemetryFrame, history: deque) -> HypothesisResult:
    c = frame.command_state
    if not c.dosing_active:
        return HypothesisResult(
            name="DOSING_FAULT", label="Dosing Pump Fault",
            confidence=0.0,
            evidence=["P-102 dosing is commanded OFF — dosing fault hypothesis does not apply"],
        )

    flow = frame.primary.flow_rate
    conc = frame.primary.chemical_concentration
    evidence: list[str] = []
    scores: list[float] = []
    weights: list[float] = []

    # 1. Adequate carrier flow (rules out DOSING_FLOW_SAFETY as explanation)
    if flow >= MIN_FLOW_FOR_DOSING:
        evidence.append(f"FT-101 = {flow:.1f} L/min — adequate carrier flow present")
        scores.append(0.7)
    else:
        evidence.append(
            f"FT-101 = {flow:.1f} L/min — low flow may explain concentration issue "
            f"(see DOSING_FLOW_SAFETY)"
        )
        scores.append(0.1)
    weights.append(0.20)

    # 2. AT-101 far from dosing equilibrium
    deviation = abs(conc - NOMINAL_CONCENTRATION)
    if deviation > 0.5:
        evidence.append(
            f"AT-101 = {conc:.3f} mg/L — {deviation:.2f} mg/L from expected "
            f"nominal {NOMINAL_CONCENTRATION} mg/L with dosing active"
        )
        scores.append(_clamp(deviation / NOMINAL_CONCENTRATION))
    elif deviation > 0.2:
        evidence.append(f"AT-101 = {conc:.3f} mg/L — moderate deviation from nominal")
        scores.append(0.3)
    else:
        evidence.append(f"AT-101 = {conc:.3f} mg/L — near nominal, dosing appears functional")
        scores.append(0.0)
    weights.append(0.50)

    # 3. Concentration not converging toward nominal
    if len(history) >= 5:
        hist_list = list(history)
        recent = [abs(NOMINAL_CONCENTRATION - f.primary.chemical_concentration) for f in hist_list[-5:]]
        if recent[-1] >= recent[0]:
            evidence.append(f"AT-101 not converging toward nominal over last {len(recent)} ticks")
            scores.append(0.7)
        else:
            evidence.append("AT-101 trending toward nominal — may be startup transient, not fault")
            scores.append(0.1)
    else:
        evidence.append("Insufficient history to assess convergence trend")
        scores.append(0.3)
    weights.append(0.30)

    confidence = _clamp(sum(s * w for s, w in zip(scores, weights)))
    return HypothesisResult(
        name="DOSING_FAULT", label="Dosing Pump Fault",
        confidence=round(confidence, 3), evidence=evidence,
    )


def score_valve_fault(frame: TelemetryFrame, history: deque) -> HypothesisResult:
    c = frame.command_state
    flow = frame.primary.flow_rate
    power = frame.secondary.pump_power_draw
    pressure = frame.primary.downstream_pressure
    evidence: list[str] = []
    scores: list[float] = []
    weights: list[float] = []

    # 1. Valve commanded open but flow near zero
    if c.valve_open or c.bypass_open:
        if flow < MIN_FLOW_FOR_DOSING:
            evidence.append(
                f"V-101/V-102 commanded open, but FT-101 = {flow:.1f} L/min — "
                f"valve may not have actuated"
            )
            scores.append(0.9)
        elif flow < NOMINAL_FLOW * 0.5:
            evidence.append(
                f"V-101/V-102 open, FT-101 = {flow:.1f} L/min — "
                f"partial valve travel or downstream obstruction"
            )
            scores.append(0.5)
        else:
            evidence.append(f"V-101/V-102 open, FT-101 = {flow:.1f} L/min — flow consistent with command")
            scores.append(0.0)
    else:
        evidence.append("No valve commanded open — valve fault hypothesis less applicable")
        scores.append(0.05)
    weights.append(0.60)

    # 2. Pump active with healthy power (isolates fault to valve, not pump)
    if c.pump_commanded and power > IDLE_POWER * 2:
        evidence.append(
            f"Pump P-101 ON with PM-101 = {power:.3f} kW — "
            f"pump driving normally, fault isolated to valve"
        )
        scores.append(0.8)
    elif c.pump_commanded:
        evidence.append(f"Pump commanded ON but PM-101 = {power:.3f} kW — pump fault cannot be excluded")
        scores.append(0.2)
    else:
        evidence.append("Pump P-101 OFF — low flow expected, valve fault hypothesis weak")
        scores.append(0.0)
    weights.append(0.25)

    # 3. Pressure inconsistent with valve position
    if (c.valve_open or c.bypass_open) and c.pump_commanded and pressure < NOMINAL_PRESSURE * 0.4:
        evidence.append(
            f"PT-101 = {pressure:.3f} bar — low pressure with pump on and valve "
            f"commanded open suggests physical blockage or stuck valve"
        )
        scores.append(0.7)
    else:
        evidence.append(f"PT-101 = {pressure:.3f} bar — pressure not conclusive for valve blockage")
        scores.append(0.2)
    weights.append(0.15)

    confidence = _clamp(sum(s * w for s, w in zip(scores, weights)))
    return HypothesisResult(
        name="VALVE_FAULT", label="Valve Actuator Fault",
        confidence=round(confidence, 3), evidence=evidence,
    )
