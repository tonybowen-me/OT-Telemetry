"""DHALSIM dataset ingestion + STEP normalisation + relevance filter.

The lab (datasets/lab/generate_datasets.py) writes, per scenario, a
``ground_truth.csv`` and a ``reported.csv`` plus a ``meta.yaml``. This module:

  1. loads those recorded artifacts (the app never runs the simulator itself),
  2. normalises rows into canonical :class:`Frame` objects (the STEP step), and
  3. applies a relevance filter -- keeping only the fields that define or change
     tank state, which is what PILOT reasons over.

PILOT only ever sees the *reported* stream. Ground truth is loaded purely so the
UI can draw "actual vs reported" and so tests can assert against physical truth.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Optional

import yaml

from .config import DATASETS_DIR
from .models import Frame, ScenarioMeta

# Fields that define or change tank/hydraulic state. Anything else in a DHALSIM
# export (network counters, packet stats, unrelated junctions) is discarded here.
RELEVANT_FIELDS = {
    "iteration", "timestamp", "tank_level", "pump1_flow", "pump2_flow",
    "pump1_status", "pump2_status", "tank_inflow", "total_demand",
    "pressure_J39", "pressure_J156", "pressure_J280", "attack_flag", "missing",
}

_FLOAT_FIELDS = {
    "tank_level", "pump1_flow", "pump2_flow", "tank_inflow", "total_demand",
    "pressure_J39", "pressure_J156", "pressure_J280",
}
_INT_FIELDS = {"iteration", "timestamp", "pump1_status", "pump2_status", "attack_flag", "missing"}


def _parse_cell(key: str, raw: str):
    raw = (raw or "").strip()
    if raw == "":
        return None
    if key in _FLOAT_FIELDS:
        try:
            v = float(raw)
        except ValueError:
            return None
        return None if math.isnan(v) else v
    if key in _INT_FIELDS:
        try:
            return int(float(raw))
        except ValueError:
            return None
    return raw


def load_frames(csv_path: Path) -> list[Frame]:
    """Load a CSV into canonical frames, applying the relevance filter."""
    frames: list[Frame] = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            filtered = {k: _parse_cell(k, v) for k, v in row.items() if k in RELEVANT_FIELDS}
            filtered.setdefault("attack_flag", 0)
            filtered.setdefault("missing", 0)
            if filtered.get("attack_flag") is None:
                filtered["attack_flag"] = 0
            if filtered.get("missing") is None:
                filtered["missing"] = 0
            frames.append(Frame(**filtered))
    return frames


def load_meta(scenario_dir: Path) -> ScenarioMeta:
    with (scenario_dir / "meta.yaml").open() as f:
        raw = yaml.safe_load(f)
    return ScenarioMeta(
        id=raw["id"],
        name=raw["name"],
        description=raw["description"],
        scenario_class=raw["class"],
        attack=raw.get("attack"),
        expected_pilot=raw["expected_pilot"],
        expected_sigma=raw["expected_sigma"],
        narrative=raw["narrative"],
        step_seconds=raw.get("step_seconds", 300),
        steps=raw.get("steps", 0),
    )


class Scenario:
    def __init__(self, scenario_dir: Path):
        self.dir = scenario_dir
        self.meta = load_meta(scenario_dir)
        self.reported = load_frames(scenario_dir / "reported.csv")
        self.ground_truth = load_frames(scenario_dir / "ground_truth.csv")


def list_scenarios(root: Optional[Path] = None) -> list[str]:
    root = root or DATASETS_DIR
    out = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / "meta.yaml").exists():
            out.append(d.name)
    return out


def load_scenario(scenario_id: str, root: Optional[Path] = None) -> Scenario:
    root = root or DATASETS_DIR
    d = root / scenario_id
    if not (d / "meta.yaml").exists():
        raise FileNotFoundError(f"Unknown scenario: {scenario_id!r}")
    return Scenario(d)
