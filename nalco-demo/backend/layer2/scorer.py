from __future__ import annotations

from simulator.models import TelemetryFrame
from .models import Layer2Result, SensorScore
from .predictor import predict

# EMA smoothing — lower = slower to react, better for slow drift detection
SMOOTHING = 0.15

WARN_THRESHOLD = 0.75   # score below this → warn
FAIL_THRESHOLD = 0.50   # score below this → fail
ESCALATE_TICKS = 5      # consecutive fail ticks on any sensor triggers Layer 3 escalation

TREND_DELTA = 0.02      # minimum score change per tick to register as degrading/recovering

SENSOR_NAMES: dict[str, str] = {
    "FT-101": "Flow Rate",
    "PT-101": "Downstream Pressure",
    "AT-101": "Chlorine Residual",
    "PM-101": "Pump Power Draw",
    "CT-101": "Downstream Conductivity",
}


class ResidualScorer:
    def __init__(self) -> None:
        self._scores: dict[str, float] = {}
        self._prev_scores: dict[str, float] = {}
        self._fail_ticks: dict[str, int] = {}

    def score(self, frame: TelemetryFrame) -> Layer2Result:
        predictions = predict(frame)
        sensor_scores: list[SensorScore] = []

        for pred in predictions:
            residual = abs(pred.observed - pred.predicted) / pred.expected_range
            raw_trust = max(0.0, 1.0 - residual)

            prev = self._scores.get(pred.tag, 1.0)
            rolling = SMOOTHING * raw_trust + (1 - SMOOTHING) * prev
            self._scores[pred.tag] = rolling

            prev_score = self._prev_scores.get(pred.tag, rolling)
            delta = rolling - prev_score
            if delta < -TREND_DELTA:
                trend = "degrading"
            elif delta > TREND_DELTA:
                trend = "recovering"
            else:
                trend = "stable"
            self._prev_scores[pred.tag] = rolling

            if rolling >= WARN_THRESHOLD:
                verdict: str = "pass"
            elif rolling >= FAIL_THRESHOLD:
                verdict = "warn"
            else:
                verdict = "fail"

            if verdict == "fail":
                self._fail_ticks[pred.tag] = self._fail_ticks.get(pred.tag, 0) + 1
            else:
                self._fail_ticks[pred.tag] = 0

            sensor_scores.append(SensorScore(
                tag=pred.tag,
                name=SENSOR_NAMES[pred.tag],
                trust_score=round(rolling, 3),
                raw_residual=round(residual, 3),
                predicted=round(pred.predicted, 3),
                observed=round(pred.observed, 3),
                trend=trend,
                verdict=verdict,
            ))

        verdicts = [s.verdict for s in sensor_scores]
        if "fail" in verdicts:
            overall = "fail"
        elif "warn" in verdicts:
            overall = "warn"
        else:
            overall = "pass"

        escalate = any(
            self._fail_ticks.get(s.tag, 0) >= ESCALATE_TICKS
            for s in sensor_scores
        )

        return Layer2Result(
            verdict=overall,
            sensors=sensor_scores,
            escalate_to_layer3=escalate,
        )
