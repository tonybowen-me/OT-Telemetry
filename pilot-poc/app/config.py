"""Central, explainable configuration for the PILOT demo.

Every threshold used by the reasoning path lives here so the logic stays
deterministic and auditable (no hidden constants, no ML).
"""
from __future__ import annotations

import math
from pathlib import Path

# --- Paths --------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS_DIR = REPO_ROOT / "datasets"

# --- Minitown physical constants (from the DHALSIM topology) ------------------
TANK_DIAMETER_M = 31.3
TANK_AREA_M2 = math.pi * (TANK_DIAMETER_M / 2.0) ** 2
TANK_MAX_LEVEL_M = 6.5
TANK_MIN_LEVEL_M = 0.0
STEP_SECONDS = 300

# Pump control thresholds (minitown [CONTROLS])
P1_ON_BELOW, P1_OFF_ABOVE = 4.0, 6.3
P2_ON_BELOW, P2_OFF_ABOVE = 1.0, 4.5

# --- PILOT Layer 1 invariant tolerances ---------------------------------------
# Mass balance: allowed slack between reported level change and the change implied
# by the reported tank inflow, per step (metres). Covers sensor noise + numerical.
MASS_BALANCE_TOLERANCE_M = 0.03
# A violation must persist to avoid single-sample false positives.
SUSTAINED_VIOLATION_STEPS = 2
# Pump energy consistency: a running pump must move at least this flow (m^3/s).
PUMP_MIN_FLOW_M3S = 1e-4
# Insufficient data: uncertain if the level tag is missing for at least this many steps.
MIN_LEVEL_COVERAGE_STEPS = 2

# --- Operational (non-security) finding thresholds ----------------------------
LOW_TANK_LEVEL_M = 1.0
LOW_PRESSURE_M = 15.0
# J280 sits at a naturally low static pressure (~3 m) even under nominal
# operation, so it is not used as a low-pressure health signal.
PRESSURE_JUNCTIONS = ["pressure_J39", "pressure_J156"]

# --- Layer 2 residual scoring -------------------------------------------------
L2_SMOOTHING = 0.3
L2_WARN_THRESHOLD = 0.75
L2_FAIL_THRESHOLD = 0.5
L2_ESCALATE_STEPS = 3

# --- Layer 3 -------------------------------------------------------------------
L3_CONFIDENCE_THRESHOLD = 0.5
