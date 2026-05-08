from __future__ import annotations

from typing import Optional

from simulator.models import TelemetryFrame
from .invariants import (
    check_dosing_flow_safety,
    check_energy_consistency,
    check_flow_continuity,
    check_pressure_causality,
    check_temporal_ordering,
)
from .models import Layer1Result


class InvariantChecker:
    def __init__(self) -> None:
        self._prev_frame: Optional[TelemetryFrame] = None

    def check(self, frame: TelemetryFrame) -> Layer1Result:
        results = [
            check_flow_continuity(frame),
            check_pressure_causality(frame),
            check_dosing_flow_safety(frame),
            check_energy_consistency(frame),
            check_temporal_ordering(frame, self._prev_frame),
        ]
        self._prev_frame = frame

        violations = [r for r in results if r.status == "fail"]
        evaluated = len([r for r in results if r.status != "not_applicable"])

        return Layer1Result(
            verdict="fail" if violations else "pass",
            rules_evaluated=evaluated,
            violations=violations,
            all_results=results,
        )
