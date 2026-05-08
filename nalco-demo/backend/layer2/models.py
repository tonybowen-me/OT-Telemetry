from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SensorScore(BaseModel):
    tag: str
    name: str
    trust_score: float
    raw_residual: float
    predicted: float
    observed: float
    trend: Literal["stable", "degrading", "recovering"]
    verdict: Literal["pass", "warn", "fail"]


class Layer2Result(BaseModel):
    verdict: Literal["pass", "warn", "fail"]
    sensors: list[SensorScore]
    escalate_to_layer3: bool
