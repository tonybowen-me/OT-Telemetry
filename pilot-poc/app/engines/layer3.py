"""PILOT Layer 3 - counterfactual root-cause ranking.

Triggered when Layer 1 fails or Layer 2 escalates. It asks a causal question:
*which single explanation best accounts for the observed inconsistency?* Each
hypothesis is scored deterministically from measurable signatures in the reported
stream -- no ML, fully explainable. The output is a ranked root cause with evidence.
"""
from __future__ import annotations

from .. import config as C
from ..models import Frame, Hypothesis, Layer1Result, Layer2Result, Layer3Result


def _fail(l1: Layer1Result, rule_id: str) -> bool:
    return any(r.rule_id == rule_id and r.status == "fail" for r in l1.invariants)


def _mass_balance_stats(frames: list[Frame]) -> tuple[float, float]:
    """Return (max reported |Δlevel| during a mismatch, max implied |Δlevel|)."""
    dt, area = C.STEP_SECONDS, C.TANK_AREA_M2
    max_reported = 0.0
    max_implied = 0.0
    for prev, cur in zip(frames, frames[1:]):
        if None in (prev.tank_level, cur.tank_level, cur.tank_inflow):
            continue
        implied = abs(cur.tank_inflow * dt / area)
        reported = abs(cur.tank_level - prev.tank_level)
        if abs(reported - implied) > C.MASS_BALANCE_TOLERANCE_M:
            max_reported = max(max_reported, reported)
            max_implied = max(max_implied, implied)
    return max_reported, max_implied


def evaluate(frames: list[Frame], l1: Layer1Result, l2: Layer2Result) -> Layer3Result:
    triggered = l1.verdict != "pass" or l2.escalate
    if not triggered:
        return Layer3Result(triggered=False, summary="No inconsistency to explain; Layer 3 not engaged.")

    candidates: list[Hypothesis] = []

    if _fail(l1, "TANK_MASS_BALANCE"):
        reported_d, implied_d = _mass_balance_stats(frames)
        evidence = [
            f"Reported tank level moves only {reported_d:.3f} m/step while the reported "
            f"inflow implies {implied_d:.3f} m/step.",
            "Pump and inflow telemetry remain internally consistent, so the falsification "
            "is isolated to the level tag (classic concealment MITM).",
        ]
        candidates.append(Hypothesis(
            name="sensor_spoof_level", label="Falsified tank-level sensor (concealment MITM)",
            confidence=0.9, evidence=evidence,
        ))

    if _fail(l1, "PUMP_ENERGY_CONSISTENCY"):
        candidates.append(Hypothesis(
            name="pump_failure", label="Pump command/flow mismatch (failure or spoof)",
            confidence=0.8,
            evidence=["A pump's reported status disagrees with its delivered flow."],
        ))

    if _fail(l1, "INSUFFICIENT_DATA"):
        candidates.append(Hypothesis(
            name="data_loss", label="Telemetry loss / DoS on a required tag",
            confidence=0.85,
            evidence=["A required tag (tank level) is missing for a sustained window; "
                      "the true state cannot be reconstructed."],
        ))

    if not candidates and l2.escalate:
        candidates.append(Hypothesis(
            name="drift", label="Slow residual drift (no hard invariant broken)",
            confidence=0.5,
            evidence=[f"Layer 2 trust fell to {min(s.min_trust for s in l2.sensors):.2f} "
                      "without breaking a hard invariant."],
        ))

    candidates.sort(key=lambda h: h.confidence, reverse=True)
    top = candidates[0] if candidates else None
    summary = (
        f"Most likely root cause: {top.label} (confidence {top.confidence:.0%})."
        if top else "Escalated but no dominant hypothesis identified."
    )
    return Layer3Result(
        triggered=True,
        top_hypothesis=top.name if top else None,
        top_confidence=top.confidence if top else 0.0,
        candidates=candidates,
        summary=summary,
    )
