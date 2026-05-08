from __future__ import annotations

from typing import Optional

from simulator.models import TelemetryFrame
from .models import InvariantResult

# ---------------------------------------------------------------------------
# Tolerances — based on sensor accuracy + hydraulic lag in this plant
# ---------------------------------------------------------------------------
LEAKAGE_THRESHOLD = 2.5       # L/min — max flow when both valves are fully closed
MIN_FLOW_FOR_DOSING = 5.0     # L/min — minimum safe flow for dosing in normal mode
PUMP_IDLE_THRESHOLD = 0.20    # kW    — below this with pump commanded on = failure
MAX_PRESSURE_WHEN_OFF = 1.5   # bar   — max tolerable residual pressure with pump off
MAX_CONCENTRATION_DELTA = 0.15  # mg/L per tick — physical ceiling given first-order lag


def check_flow_continuity(frame: TelemetryFrame) -> InvariantResult:
    """
    If V-101 and V-102 are both closed, FT-101 cannot exceed leakage threshold.
    Catches: sensor_spoof — valve closed but FT-101 falsified to show full flow.
    """
    c = frame.command_state

    if c.valve_open or c.bypass_open:
        return InvariantResult(
            rule_id="FLOW_CONTINUITY",
            status="not_applicable",
            variables=["FT-101", "V-101", "V-102"],
            expected="N/A — at least one valve is open",
            observed=f"FT-101 = {frame.primary.flow_rate:.1f} L/min",
            explanation="At least one valve is open. Flow continuity check does not apply.",
        )

    flow = frame.primary.flow_rate
    if flow > LEAKAGE_THRESHOLD:
        return InvariantResult(
            rule_id="FLOW_CONTINUITY",
            status="fail",
            variables=["FT-101", "V-101", "V-102"],
            expected=f"FT-101 ≤ {LEAKAGE_THRESHOLD} L/min (both valves closed)",
            observed=f"FT-101 = {flow:.1f} L/min",
            explanation=(
                f"V-101 and V-102 are both closed. Downstream flow cannot exceed the "
                f"leakage threshold of {LEAKAGE_THRESHOLD} L/min. "
                f"Reported {flow:.1f} L/min is physically impossible — "
                f"FT-101 reading is likely falsified."
            ),
        )

    return InvariantResult(
        rule_id="FLOW_CONTINUITY",
        status="pass",
        variables=["FT-101", "V-101", "V-102"],
        expected=f"FT-101 ≤ {LEAKAGE_THRESHOLD} L/min",
        observed=f"FT-101 = {flow:.1f} L/min",
        explanation="Flow within leakage bounds with both valves closed.",
    )


def check_pressure_causality(frame: TelemetryFrame) -> InvariantResult:
    """
    If P-101 is commanded off, PT-101 cannot exceed residual decay threshold.
    Catches: scenarios where pressure is artificially elevated with no pump source.
    """
    c = frame.command_state

    if c.pump_commanded:
        return InvariantResult(
            rule_id="PRESSURE_CAUSALITY",
            status="not_applicable",
            variables=["PT-101", "P-101"],
            expected="N/A — pump is commanded on",
            observed=f"PT-101 = {frame.primary.downstream_pressure:.3f} bar",
            explanation="Pump is active. Pressure causality check does not apply.",
        )

    pressure = frame.primary.downstream_pressure
    if pressure > MAX_PRESSURE_WHEN_OFF:
        return InvariantResult(
            rule_id="PRESSURE_CAUSALITY",
            status="fail",
            variables=["PT-101", "P-101"],
            expected=f"PT-101 ≤ {MAX_PRESSURE_WHEN_OFF} bar (pump off, residual decay)",
            observed=f"PT-101 = {pressure:.3f} bar",
            explanation=(
                f"P-101 is commanded off with no upstream pressure source active. "
                f"PT-101 reads {pressure:.3f} bar — above the residual decay threshold "
                f"of {MAX_PRESSURE_WHEN_OFF} bar. Reading may be falsified or an "
                f"untracked pressure source is present."
            ),
        )

    return InvariantResult(
        rule_id="PRESSURE_CAUSALITY",
        status="pass",
        variables=["PT-101", "P-101"],
        expected=f"PT-101 ≤ {MAX_PRESSURE_WHEN_OFF} bar",
        observed=f"PT-101 = {pressure:.3f} bar",
        explanation="Pressure within expected residual range with pump off.",
    )


def check_dosing_flow_safety(frame: TelemetryFrame) -> InvariantResult:
    """
    Chemical dosing active while flow is below minimum is invalid unless recirculation mode.
    Catches: dosing into near-zero flow in normal mode — unsafe concentration buildup.
    Also fires during pump_failure once flow decays below threshold.
    """
    c = frame.command_state

    if frame.operating_mode == "recirculation":
        return InvariantResult(
            rule_id="DOSING_FLOW_SAFETY",
            status="not_applicable",
            variables=["P-102", "FT-101", "mode"],
            expected="N/A — recirculation mode permits dosing at low flow",
            observed=f"FT-101 = {frame.primary.flow_rate:.1f} L/min, mode = recirculation",
            explanation="Recirculation mode explicitly permits dosing independent of main flow.",
        )

    if not c.dosing_active:
        return InvariantResult(
            rule_id="DOSING_FLOW_SAFETY",
            status="not_applicable",
            variables=["P-102", "FT-101"],
            expected="N/A — dosing pump is off",
            observed=f"FT-101 = {frame.primary.flow_rate:.1f} L/min",
            explanation="Dosing is not active. Safety constraint does not apply.",
        )

    flow = frame.primary.flow_rate
    if flow < MIN_FLOW_FOR_DOSING:
        return InvariantResult(
            rule_id="DOSING_FLOW_SAFETY",
            status="fail",
            variables=["P-102", "FT-101", "mode"],
            expected=f"FT-101 ≥ {MIN_FLOW_FOR_DOSING} L/min when dosing active in normal mode",
            observed=f"FT-101 = {flow:.1f} L/min, mode = {frame.operating_mode}",
            explanation=(
                f"P-102 dosing pump is active in normal mode but FT-101 reports {flow:.1f} L/min. "
                f"Dosing into near-zero flow causes unsafe chemical concentration buildup. "
                f"Either the dosing command is erroneous or the flow reading is unreliable."
            ),
        )

    return InvariantResult(
        rule_id="DOSING_FLOW_SAFETY",
        status="pass",
        variables=["P-102", "FT-101"],
        expected=f"FT-101 ≥ {MIN_FLOW_FOR_DOSING} L/min",
        observed=f"FT-101 = {flow:.1f} L/min",
        explanation="Sufficient flow present for safe chemical dosing.",
    )


def check_energy_consistency(frame: TelemetryFrame) -> InvariantResult:
    """
    P-101 commanded on must produce non-idle power draw on PM-101.
    Catches: pump_failure — commanded on, mechanically dead, PM-101 stays at idle.
    """
    c = frame.command_state

    if not c.pump_commanded:
        return InvariantResult(
            rule_id="ENERGY_CONSISTENCY",
            status="not_applicable",
            variables=["PM-101", "P-101"],
            expected="N/A — pump is commanded off",
            observed=f"PM-101 = {frame.secondary.pump_power_draw:.3f} kW",
            explanation="Pump is commanded off. Energy consistency check does not apply.",
        )

    power = frame.secondary.pump_power_draw
    if power < PUMP_IDLE_THRESHOLD:
        return InvariantResult(
            rule_id="ENERGY_CONSISTENCY",
            status="fail",
            variables=["PM-101", "P-101"],
            expected=f"PM-101 > {PUMP_IDLE_THRESHOLD} kW (pump commanded on)",
            observed=f"PM-101 = {power:.3f} kW (at idle)",
            explanation=(
                f"P-101 is commanded ON but PM-101 reads {power:.3f} kW — "
                f"consistent with standby draw (~0.08 kW), not active pumping (~3.0 kW). "
                f"The pump is not responding to its command. Mechanical failure or actuator fault."
            ),
        )

    return InvariantResult(
        rule_id="ENERGY_CONSISTENCY",
        status="pass",
        variables=["PM-101", "P-101"],
        expected=f"PM-101 > {PUMP_IDLE_THRESHOLD} kW",
        observed=f"PM-101 = {power:.3f} kW",
        explanation="Power draw consistent with pump command state.",
    )


def check_temporal_ordering(
    frame: TelemetryFrame,
    prev_frame: Optional[TelemetryFrame],
) -> InvariantResult:
    """
    Concentration change per tick cannot exceed the physical maximum given tank residence time.
    A step change larger than the first-order lag model permits is physically impossible.
    Catches: direct AT-101 manipulation (large sudden jumps, not slow drift).
    """
    if prev_frame is None:
        return InvariantResult(
            rule_id="TEMPORAL_ORDERING",
            status="not_applicable",
            variables=["AT-101"],
            expected="N/A — no prior frame available",
            observed=f"AT-101 = {frame.primary.chemical_concentration:.3f} mg/L",
            explanation="First tick — no previous reading available for delta check.",
        )

    delta = abs(
        frame.primary.chemical_concentration
        - prev_frame.primary.chemical_concentration
    )

    if delta > MAX_CONCENTRATION_DELTA:
        return InvariantResult(
            rule_id="TEMPORAL_ORDERING",
            status="fail",
            variables=["AT-101"],
            expected=f"Δconcentration ≤ {MAX_CONCENTRATION_DELTA} mg/L per tick",
            observed=f"Δconcentration = {delta:.3f} mg/L  (prev={prev_frame.primary.chemical_concentration:.3f}, curr={frame.primary.chemical_concentration:.3f})",
            explanation=(
                f"AT-101 changed by {delta:.3f} mg/L in a single tick. "
                f"Physical maximum given tank residence time and first-order lag is "
                f"{MAX_CONCENTRATION_DELTA} mg/L per tick. "
                f"This rate of change has no physical cause — AT-101 may be directly manipulated."
            ),
        )

    return InvariantResult(
        rule_id="TEMPORAL_ORDERING",
        status="pass",
        variables=["AT-101"],
        expected=f"Δconcentration ≤ {MAX_CONCENTRATION_DELTA} mg/L per tick",
        observed=f"Δconcentration = {delta:.3f} mg/L",
        explanation="Concentration change within physically plausible bounds.",
    )
