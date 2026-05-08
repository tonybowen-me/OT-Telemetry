from __future__ import annotations

from collections import deque

from simulator.models import TelemetryFrame
from layer2.models import Layer2Result
from .models import Layer3Result
from .hypotheses import (
    score_dosing_fault,
    score_pump_failure,
    score_replay_attack,
    score_sensor_spoof,
    score_slow_drift,
    score_valve_fault,
)

HISTORY_SIZE = 20
CONFIDENCE_THRESHOLD = 0.50


class CounterfactualEngine:
    def __init__(self) -> None:
        self._history: deque[TelemetryFrame] = deque(maxlen=HISTORY_SIZE)

    def evaluate(self, frame: TelemetryFrame, layer2: Layer2Result) -> Layer3Result:
        self._history.append(frame)

        if not layer2.escalate_to_layer3:
            return Layer3Result(
                triggered=False,
                summary="Layer 2 escalation threshold not reached.",
            )

        candidates = [
            score_sensor_spoof(frame, self._history),
            score_pump_failure(frame, self._history),
            score_slow_drift(frame, self._history),
            score_replay_attack(frame, self._history),
            score_dosing_fault(frame, self._history),
            score_valve_fault(frame, self._history),
        ]
        candidates.sort(key=lambda h: h.confidence, reverse=True)
        top = candidates[0]

        if top.confidence >= CONFIDENCE_THRESHOLD:
            summary = f"Best match: {top.label} — {top.confidence*100:.0f}% confidence"
            top_name = top.name
        else:
            summary = (
                f"No hypothesis reached {CONFIDENCE_THRESHOLD*100:.0f}% confidence — inconclusive"
            )
            top_name = None

        return Layer3Result(
            triggered=True,
            top_hypothesis=top_name,
            top_confidence=top.confidence,
            candidates=candidates,
            summary=summary,
        )
