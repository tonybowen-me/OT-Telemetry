"""Orchestrates PILOT (L1-L3) + Sigma and assembles the output contract."""
from __future__ import annotations

from ..ingestion import Scenario
from ..models import EvaluationResult, Frame, PilotStatus
from . import layer1, layer2, layer3, sigma
from .. import config as C

_VERDICT_TO_STATUS: dict[str, PilotStatus] = {
    "pass": "valid", "fail": "violation", "uncertain": "uncertain",
}


def _sustained_indices(flags: list[bool], need: int = 2) -> bool:
    run = 0
    for f in flags:
        run = run + 1 if f else 0
        if run >= need:
            return True
    return False


def _operational_findings(frames: list[Frame]) -> list[str]:
    """Genuine process-health observations from reported telemetry (not security)."""
    findings: list[str] = []
    low_level = [f.tank_level is not None and f.tank_level < C.LOW_TANK_LEVEL_M for f in frames]
    if _sustained_indices(low_level):
        first = next(f.iteration for f, fl in zip(frames, low_level) if fl)
        findings.append(
            f"Tank level fell below {C.LOW_TANK_LEVEL_M} m (first at iteration {first}) - "
            "risk of running the tank dry."
        )
    for tag in C.PRESSURE_JUNCTIONS:
        vals = [getattr(f, tag) for f in frames]
        low = [v is not None and v < C.LOW_PRESSURE_M for v in vals]
        if _sustained_indices(low):
            first = next(f.iteration for f, fl in zip(frames, low) if fl)
            findings.append(
                f"Low downstream pressure at {tag.replace('pressure_', '')} "
                f"(< {C.LOW_PRESSURE_M} m, first at iteration {first})."
            )
    return findings


def _explanations(status: PilotStatus, l1, l3, findings, sig, meta) -> list[str]:
    out: list[str] = []
    if status == "violation":
        for r in l1.invariants:
            if r.status == "fail" and r.rule_id != "INSUFFICIENT_DATA":
                out.append(f"[{r.rule_id}] {r.explanation}")
        if l3.top_hypothesis:
            out.append(l3.summary)
    elif status == "uncertain":
        for r in l1.invariants:
            if r.rule_id == "INSUFFICIENT_DATA" and r.status == "fail":
                out.append(f"[{r.rule_id}] {r.explanation}")
    else:
        out.append("All PILOT invariants hold: the reported telemetry is physically "
                   "self-consistent, so it is accepted as valid.")
    if findings:
        out.append("Operational findings (separate from data integrity): " + " ".join(findings))
    if not findings and status == "valid":
        out.append("No operational concerns detected.")
    return out


def _comparison(status: PilotStatus, sig, meta) -> str:
    sig_txt = (f"raised a {sig.highest_level} alert ({len(sig.triggered_rules)} rule(s))"
               if sig.alert else "stayed silent (no rule matched)")
    if status == "violation" and not sig.alert:
        return (
            f"PILOT flags a causal VIOLATION while the correlational baseline {sig_txt}. "
            "The falsified telemetry is in-band on every threshold, so the correlational "
            "tool has nothing to match; PILOT catches it because the reported values are "
            "physically impossible."
        )
    if status == "valid" and sig.alert:
        return (
            f"PILOT returns VALID while the correlational baseline {sig_txt}. The physical "
            "event is real and honestly reported, so PILOT confirms feasibility and files it "
            "as an operational finding - not a data-integrity violation - whereas the "
            "correlational tool fires on the threshold breach."
        )
    if status == "uncertain":
        return (
            f"PILOT returns UNCERTAIN (required data missing) while the correlational baseline "
            f"{sig_txt}. PILOT refuses to assert valid or violation without the data."
        )
    if status == "valid" and not sig.alert:
        return "Both agree: nothing to report. PILOT VALID and the correlational baseline silent."
    return f"PILOT: {status}. Correlational baseline {sig_txt}."


def _evidence(scenario: Scenario, l1) -> dict:
    rep = scenario.reported
    gt = scenario.ground_truth
    def series(frames, attr):
        return [getattr(f, attr) for f in frames]
    mb = next((r for r in l1.invariants if r.rule_id == "TANK_MASS_BALANCE"), None)
    return {
        "iterations": series(rep, "iteration"),
        "reported_tank_level": series(rep, "tank_level"),
        "actual_tank_level": series(gt, "tank_level"),
        "tank_inflow": series(rep, "tank_inflow"),
        "total_demand": series(rep, "total_demand"),
        "pressure_J39_reported": series(rep, "pressure_J39"),
        "pressure_J39_actual": series(gt, "pressure_J39"),
        "attack_flag": series(rep, "attack_flag"),
        "mass_balance_first_violation": mb.first_violation_iteration if mb else None,
    }


def evaluate_scenario(scenario: Scenario) -> EvaluationResult:
    frames = scenario.reported
    l1 = layer1.evaluate(frames)
    l2 = layer2.evaluate(frames)
    l3 = layer3.evaluate(frames, l1, l2)
    sig = sigma.evaluate(frames)

    status = _VERDICT_TO_STATUS[l1.verdict]
    findings = _operational_findings(frames)
    explanations = _explanations(status, l1, l3, findings, sig, scenario.meta)
    comparison = _comparison(status, sig, scenario.meta)

    return EvaluationResult(
        scenario_id=scenario.meta.id,
        scenario_name=scenario.meta.name,
        scenario_class=scenario.meta.scenario_class,
        pilot_status=status,
        operational_findings=findings,
        layer1=l1, layer2=l2, layer3=l3, sigma=sig,
        explanations=explanations,
        evidence=_evidence(scenario, l1),
        comparison=comparison,
        timesteps=len(frames),
    )
