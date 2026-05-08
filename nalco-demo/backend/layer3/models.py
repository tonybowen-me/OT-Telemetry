from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class HypothesisResult(BaseModel):
    name: str
    label: str
    confidence: float
    evidence: list[str]


class Layer3Result(BaseModel):
    triggered: bool
    top_hypothesis: Optional[str] = None
    top_confidence: float = 0.0
    candidates: list[HypothesisResult] = []
    summary: str = ""
