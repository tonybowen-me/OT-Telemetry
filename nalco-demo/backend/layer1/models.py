from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class InvariantResult(BaseModel):
    rule_id: str
    status: Literal["pass", "fail", "not_applicable"]
    variables: list[str]
    expected: str
    observed: str
    explanation: str


class Layer1Result(BaseModel):
    verdict: Literal["pass", "fail"]
    rules_evaluated: int
    violations: list[InvariantResult]
    all_results: list[InvariantResult]
