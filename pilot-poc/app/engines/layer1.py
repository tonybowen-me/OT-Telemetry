"""PILOT Layer 1 - deterministic invariants over the *reported* telemetry.

These are hard physics/logic rules with binary pass/fail/not-applicable outcomes.
No ML, no thresholds beyond the ones declared in config. Each rule answers a
feasibility question: *could the reported stream have been produced by the real
plant?* -- not *does it look unusual?*
"""
from __future__ import annotations

from .. import config as C
from ..models import Frame, InvariantResult, Layer1Result


def _sustained(flags: list[bool], need: int) -> tuple[bool, int, int]:
    """Return (triggered, first_index_of_triggering_run, total_violation_steps)."""
    run = 0
    first = None
    total = 0
    triggered = False
    for i, f in enumerate(flags):
        if f:
            total += 1
            run += 1
            if run >= need:
                triggered = True
                if first is None:
                    first = i - need + 1
        else:
            run = 0
    return triggered, (first if first is not None else -1), total


def check_insufficient_data(frames: list[Frame]) -> InvariantResult:
    """Uncertain if the tank-level tag is missing for a sustained window."""
    missing = [f.tank_level is None for f in frames]
    triggered, first, total = _sustained(missing, C.MIN_LEVEL_COVERAGE_STEPS)
    if triggered:
        return InvariantResult(
            rule_id="INSUFFICIENT_DATA", status="fail",
            variables=["TANK.level"],
            expected=f"tank level present for > {C.MIN_LEVEL_COVERAGE_STEPS} consecutive steps",
            observed=f"tank level missing for {total} step(s)",
            explanation=(
                f"The tank-level tag is absent for {total} step(s) (first at iteration "
                f"{frames[first].iteration}). State cannot be resolved from the reported "
                f"telemetry, so the outcome is uncertain rather than a guess."
            ),
            first_violation_iteration=frames[first].iteration if first >= 0 else None,
            violation_steps=total,
        )
    return InvariantResult(
        rule_id="INSUFFICIENT_DATA", status="pass",
        variables=["TANK.level"],
        expected="required telemetry present",
        observed="tank level present",
        explanation="All required tags are present; state is resolvable.",
    )


def check_mass_balance(frames: list[Frame]) -> InvariantResult:
    """Reported tank-level change must match the change implied by tank inflow.

    dLevel_expected = inflow(m^3/s) * dt / tank_area. If the reported level stays
    flat while the reported inflow says the tank is filling/emptying, the reported
    level is physically impossible -- the signature of a concealment MITM.
    """
    dt = C.STEP_SECONDS
    area = C.TANK_AREA_M2
    flags: list[bool] = []
    worst = 0.0
    worst_iter = None
    detail = ""
    for prev, cur in zip(frames, frames[1:]):
        if None in (prev.tank_level, cur.tank_level, cur.tank_inflow):
            flags.append(False)
            continue
        expected_d = cur.tank_inflow * dt / area
        observed_d = cur.tank_level - prev.tank_level
        err = abs(observed_d - expected_d)
        violated = err > C.MASS_BALANCE_TOLERANCE_M
        flags.append(violated)
        if violated and err > worst:
            worst = err
            worst_iter = cur.iteration
            detail = (
                f"at iteration {cur.iteration}: reported level change "
                f"{observed_d:+.3f} m/step but inflow {cur.tank_inflow:+.4f} m^3/s implies "
                f"{expected_d:+.3f} m/step (mismatch {err:.3f} m > {C.MASS_BALANCE_TOLERANCE_M} m)"
            )
    triggered, first, total = _sustained(flags, C.SUSTAINED_VIOLATION_STEPS)
    if triggered:
        return InvariantResult(
            rule_id="TANK_MASS_BALANCE", status="fail",
            variables=["TANK.level", "P15.flow"],
            expected=f"|Δlevel - inflow·dt/area| ≤ {C.MASS_BALANCE_TOLERANCE_M} m/step",
            observed=f"max mismatch {worst:.3f} m over {total} step(s)",
            explanation=(
                "Reported tank level is inconsistent with the water flowing into the "
                f"tank ({detail}). The level cannot stay flat while the plant keeps moving "
                "water; the reported level tag has been falsified."
            ),
            first_violation_iteration=worst_iter,
            violation_steps=total,
        )
    return InvariantResult(
        rule_id="TANK_MASS_BALANCE", status="pass",
        variables=["TANK.level", "P15.flow"],
        expected=f"|Δlevel - inflow·dt/area| ≤ {C.MASS_BALANCE_TOLERANCE_M} m/step",
        observed="within tolerance every step",
        explanation="Reported tank level tracks the reported inflow; mass balance holds.",
    )


def check_pump_energy(frames: list[Frame]) -> InvariantResult:
    """A pump reported ON must move flow; reported OFF must not."""
    flags: list[bool] = []
    detail = ""
    bad_iter = None
    applicable = 0
    for f in frames:
        step_bad = False
        for status, flow, tag in (
            (f.pump1_status, f.pump1_flow, "PUMP1"),
            (f.pump2_status, f.pump2_flow, "PUMP2"),
        ):
            if status is None or flow is None:
                continue
            applicable += 1
            if status == 1 and flow < C.PUMP_MIN_FLOW_M3S:
                step_bad = True
                detail = f"{tag} reported ON at iteration {f.iteration} but flow {flow:.5f} m^3/s ≈ 0"
                bad_iter = f.iteration
            if status == 0 and flow > 10 * C.PUMP_MIN_FLOW_M3S:
                step_bad = True
                detail = f"{tag} reported OFF at iteration {f.iteration} but flow {flow:.5f} m^3/s"
                bad_iter = f.iteration
        flags.append(step_bad)
    if applicable == 0:
        return InvariantResult(
            rule_id="PUMP_ENERGY_CONSISTENCY", status="not_applicable",
            variables=["PUMP1", "PUMP2"],
            expected="pump status/flow present",
            observed="pump telemetry unavailable",
            explanation="No pump status/flow telemetry to evaluate.",
        )
    triggered, first, total = _sustained(flags, C.SUSTAINED_VIOLATION_STEPS)
    if triggered:
        return InvariantResult(
            rule_id="PUMP_ENERGY_CONSISTENCY", status="fail",
            variables=["PUMP1", "PUMP2"],
            expected="status ON ⇒ flow > 0 ; status OFF ⇒ flow ≈ 0",
            observed=detail,
            explanation=f"Pump command and delivered flow disagree: {detail}.",
            first_violation_iteration=bad_iter,
            violation_steps=total,
        )
    return InvariantResult(
        rule_id="PUMP_ENERGY_CONSISTENCY", status="pass",
        variables=["PUMP1", "PUMP2"],
        expected="status ON ⇒ flow > 0 ; status OFF ⇒ flow ≈ 0",
        observed="consistent every step",
        explanation="Reported pump status and flow are energetically consistent.",
    )


def check_tank_bounds(frames: list[Frame]) -> InvariantResult:
    """Reported level must stay within the physical tank envelope."""
    flags = [
        (f.tank_level is not None and not (C.TANK_MIN_LEVEL_M - 0.05 <= f.tank_level <= C.TANK_MAX_LEVEL_M + 0.05))
        for f in frames
    ]
    triggered, first, total = _sustained(flags, 1)
    if triggered:
        bad = frames[first]
        return InvariantResult(
            rule_id="TANK_BOUNDS", status="fail",
            variables=["TANK.level"],
            expected=f"{C.TANK_MIN_LEVEL_M} m ≤ level ≤ {C.TANK_MAX_LEVEL_M} m",
            observed=f"level = {bad.tank_level:.2f} m at iteration {bad.iteration}",
            explanation=(
                f"Reported tank level {bad.tank_level:.2f} m is outside the physical tank "
                f"envelope [{C.TANK_MIN_LEVEL_M}, {C.TANK_MAX_LEVEL_M}] m."
            ),
            first_violation_iteration=bad.iteration,
            violation_steps=total,
        )
    return InvariantResult(
        rule_id="TANK_BOUNDS", status="pass",
        variables=["TANK.level"],
        expected=f"{C.TANK_MIN_LEVEL_M} m ≤ level ≤ {C.TANK_MAX_LEVEL_M} m",
        observed="within envelope",
        explanation="Reported tank level stays within the physical tank envelope.",
    )


ALL_CHECKS = (
    check_insufficient_data,
    check_mass_balance,
    check_pump_energy,
    check_tank_bounds,
)


def evaluate(frames: list[Frame]) -> Layer1Result:
    results = [chk(frames) for chk in ALL_CHECKS]
    insufficient = next(r for r in results if r.rule_id == "INSUFFICIENT_DATA")
    hard_violations = [
        r for r in results
        if r.status == "fail" and r.rule_id != "INSUFFICIENT_DATA"
    ]

    if hard_violations:
        verdict = "fail"
    elif insufficient.status == "fail":
        verdict = "uncertain"
    else:
        verdict = "pass"

    return Layer1Result(
        verdict=verdict,
        invariants=results,
        violations=[r.rule_id for r in hard_violations],
    )
