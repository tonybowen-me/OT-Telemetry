"""Canonical data models: telemetry frames and the PILOT/Sigma output contract."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

PilotStatus = Literal["valid", "violation", "uncertain"]
SigmaLevel = Literal["informational", "low", "medium", "high"]


class Frame(BaseModel):
    """One normalised telemetry sample (STEP canonical transition)."""
    iteration: int
    timestamp: int
    tank_level: Optional[float] = None      # m  (None = missing)
    pump1_flow: Optional[float] = None      # m^3/s
    pump2_flow: Optional[float] = None
    pump1_status: Optional[int] = None      # 0/1
    pump2_status: Optional[int] = None
    tank_inflow: Optional[float] = None      # m^3/s into tank (pipe P15)
    total_demand: Optional[float] = None     # L/s
    pressure_J39: Optional[float] = None
    pressure_J156: Optional[float] = None
    pressure_J280: Optional[float] = None
    attack_flag: int = 0
    missing: int = 0


class ScenarioMeta(BaseModel):
    id: str
    name: str
    description: str
    scenario_class: str
    attack: Optional[dict] = None
    expected_pilot: str
    expected_sigma: str
    narrative: str
    step_seconds: int = 300
    steps: int = 0


# --- PILOT results ------------------------------------------------------------
class InvariantResult(BaseModel):
    rule_id: str
    status: Literal["pass", "fail", "not_applicable"]
    variables: list[str]
    expected: str
    observed: str
    explanation: str
    first_violation_iteration: Optional[int] = None
    violation_steps: int = 0


class Layer1Result(BaseModel):
    verdict: Literal["pass", "fail", "uncertain"]
    invariants: list[InvariantResult]
    violations: list[str]


class SensorTrust(BaseModel):
    tag: str
    name: str
    trust_score: float
    min_trust: float
    verdict: Literal["pass", "warn", "fail"]


class Layer2Result(BaseModel):
    verdict: Literal["pass", "warn", "fail"]
    sensors: list[SensorTrust]
    escalate: bool


class Hypothesis(BaseModel):
    name: str
    label: str
    confidence: float
    evidence: list[str]


class Layer3Result(BaseModel):
    triggered: bool
    top_hypothesis: Optional[str] = None
    top_confidence: float = 0.0
    candidates: list[Hypothesis] = []
    summary: str = ""


# --- Sigma (correlational baseline) -------------------------------------------
class SigmaRuleHit(BaseModel):
    name: str
    expression: str
    level: SigmaLevel
    hit_count: int
    first_iteration: Optional[int] = None


class SigmaResult(BaseModel):
    alert: bool
    highest_level: Optional[SigmaLevel] = None
    triggered_rules: list[SigmaRuleHit]


# --- Top-level output contract ------------------------------------------------
class EvaluationResult(BaseModel):
    scenario_id: str
    scenario_name: str
    scenario_class: str
    pilot_status: PilotStatus
    operational_findings: list[str]
    layer1: Layer1Result
    layer2: Layer2Result
    layer3: Layer3Result
    sigma: SigmaResult
    explanations: list[str]
    evidence: dict
    comparison: str
    timesteps: int
