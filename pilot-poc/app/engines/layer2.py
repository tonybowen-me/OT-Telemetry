"""PILOT Layer 2 - residual trust scoring.

Layer 1 answers hard yes/no feasibility. Layer 2 tracks *how far* the reported
telemetry drifts from what the physical model expects, as a rolling per-sensor
trust score. This catches slow drift that no single step would trip, and decides
whether to escalate to the Layer 3 causal engine.
"""
from __future__ import annotations

from .. import config as C
from ..models import Frame, Layer2Result, SensorTrust


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _score_level(frames: list[Frame]) -> SensorTrust:
    """Trust the tank-level sensor by its mass-balance residual over time."""
    dt, area = C.STEP_SECONDS, C.TANK_AREA_M2
    trust = 1.0
    min_trust = 1.0
    scale = 5.0 * C.MASS_BALANCE_TOLERANCE_M
    evaluated = 0
    for prev, cur in zip(frames, frames[1:]):
        if None in (prev.tank_level, cur.tank_level, cur.tank_inflow):
            continue
        evaluated += 1
        expected_d = cur.tank_inflow * dt / area
        residual = abs((cur.tank_level - prev.tank_level) - expected_d)
        instantaneous = 1.0 - _clamp01(residual / scale)
        trust = (1 - C.L2_SMOOTHING) * trust + C.L2_SMOOTHING * instantaneous
        min_trust = min(min_trust, trust)
    verdict = "pass"
    if evaluated:
        if min_trust < C.L2_FAIL_THRESHOLD:
            verdict = "fail"
        elif min_trust < C.L2_WARN_THRESHOLD:
            verdict = "warn"
    return SensorTrust(
        tag="TANK.level", name="Tank level",
        trust_score=round(trust, 3), min_trust=round(min_trust, 3), verdict=verdict,
    )


def _score_pump(frames: list[Frame]) -> SensorTrust:
    trust = 1.0
    min_trust = 1.0
    for f in frames:
        bad = False
        for status, flow in ((f.pump1_status, f.pump1_flow), (f.pump2_status, f.pump2_flow)):
            if status is None or flow is None:
                continue
            if status == 1 and flow < C.PUMP_MIN_FLOW_M3S:
                bad = True
            if status == 0 and flow > 10 * C.PUMP_MIN_FLOW_M3S:
                bad = True
        instantaneous = 0.0 if bad else 1.0
        trust = (1 - C.L2_SMOOTHING) * trust + C.L2_SMOOTHING * instantaneous
        min_trust = min(min_trust, trust)
    verdict = "pass"
    if min_trust < C.L2_FAIL_THRESHOLD:
        verdict = "fail"
    elif min_trust < C.L2_WARN_THRESHOLD:
        verdict = "warn"
    return SensorTrust(
        tag="PUMP.flow", name="Pump flow/status", trust_score=round(trust, 3),
        min_trust=round(min_trust, 3), verdict=verdict,
    )


def evaluate(frames: list[Frame]) -> Layer2Result:
    sensors = [_score_level(frames), _score_pump(frames)]
    worst = min((s.min_trust for s in sensors), default=1.0)
    if worst < C.L2_FAIL_THRESHOLD:
        verdict = "fail"
    elif worst < C.L2_WARN_THRESHOLD:
        verdict = "warn"
    else:
        verdict = "pass"
    # Only a hard trust collapse escalates to Layer 3; a transient warn does not,
    # so an honestly-reported operational event is not treated as a root cause.
    escalate = verdict == "fail"
    return Layer2Result(verdict=verdict, sensors=sensors, escalate=escalate)
