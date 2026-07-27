"""Sigma-style correlational baseline.

This stands in for the whole class of deployed detection tooling (SIEM/Sigma/
threshold rules). It evaluates simple boolean conditions over the *reported*
telemetry only -- it has no physical model and no notion of feasibility. Its
job in this demo is to show what a correlational tool does and does not catch.
"""
from __future__ import annotations

from typing import Callable, Optional

from .. import config as C
from ..models import Frame, SigmaLevel, SigmaResult, SigmaRuleHit

_LEVEL_ORDER = {"informational": 0, "low": 1, "medium": 2, "high": 3}


class _Rule:
    def __init__(self, name: str, expression: str, level: SigmaLevel,
                 predicate: Callable[[Frame], Optional[bool]]):
        self.name = name
        self.expression = expression
        self.level = level
        self.predicate = predicate


# Reported-telemetry threshold rules. Each predicate returns None when the tag it
# needs is missing (Sigma simply has nothing to match on).
RULES = [
    _Rule("tank_level_overflow", "tank_level > 6.3", "high",
          lambda f: None if f.tank_level is None else f.tank_level > 6.3),
    _Rule("tank_level_low", "tank_level < 1.0", "high",
          lambda f: None if f.tank_level is None else f.tank_level < C.LOW_TANK_LEVEL_M),
    _Rule("low_pressure_J39", "pressure_J39 < 15", "medium",
          lambda f: None if f.pressure_J39 is None else f.pressure_J39 < C.LOW_PRESSURE_M),
    _Rule("low_pressure_J156", "pressure_J156 < 15", "medium",
          lambda f: None if f.pressure_J156 is None else f.pressure_J156 < C.LOW_PRESSURE_M),
]


def evaluate(frames: list[Frame]) -> SigmaResult:
    hits: dict[str, SigmaRuleHit] = {}
    for f in frames:
        for rule in RULES:
            matched = rule.predicate(f)
            if matched:
                if rule.name not in hits:
                    hits[rule.name] = SigmaRuleHit(
                        name=rule.name, expression=rule.expression,
                        level=rule.level, hit_count=0, first_iteration=f.iteration,
                    )
                hits[rule.name].hit_count += 1
    triggered = list(hits.values())
    triggered.sort(key=lambda h: (_LEVEL_ORDER[h.level], h.hit_count), reverse=True)
    highest = None
    if triggered:
        highest = max(triggered, key=lambda h: _LEVEL_ORDER[h.level]).level
    return SigmaResult(alert=bool(triggered), highest_level=highest, triggered_rules=triggered)
