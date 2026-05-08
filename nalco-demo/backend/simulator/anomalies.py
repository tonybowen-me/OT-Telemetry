from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .models import TelemetryFrame


class AnomalyType(str, Enum):
    NONE = "none"
    SENSOR_SPOOF = "sensor_spoof"
    SLOW_DRIFT = "slow_drift"
    PUMP_FAILURE = "pump_failure"
    REPLAY_ATTACK = "replay_attack"


@dataclass
class AnomalyState:
    type: AnomalyType = AnomalyType.NONE
    ticks_active: int = 0
    # SLOW_DRIFT: accumulated offset added to AT-101 reading each tick
    drift_accumulator: float = 0.0
    # REPLAY_ATTACK: clean frame captured on first tick, replayed thereafter
    replay_snapshot: Optional[TelemetryFrame] = None

    def reset(self) -> None:
        self.type = AnomalyType.NONE
        self.ticks_active = 0
        self.drift_accumulator = 0.0
        self.replay_snapshot = None

    @property
    def is_active(self) -> bool:
        return self.type != AnomalyType.NONE
