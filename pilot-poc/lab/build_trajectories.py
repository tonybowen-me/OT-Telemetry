#!/usr/bin/env python3
"""Offline: bake the DHALSIM minitown physical process into a compact trajectory.

This runs EPANET/WNTR (the exact hydraulic engine DHALSIM wraps) over the
third-party DHALSIM ``minitown`` topology for the two physical demand conditions
the live lab can be in -- nominal and demand-surge -- and writes them to
``lab/data/trajectory.json``.

The live utility service (``lab/service.py``) then *streams* that physical
process in real time and applies network attacks (concealment MITM / DoS) to the
SCADA-visible view live. Precomputing the physics keeps the deployed utility
lightweight (no scipy/wntr at runtime) while the numbers remain genuine EPANET
output -- exactly how DHALSIM records a run's ``ground_truth.csv``.

Run:  python3 lab/build_trajectories.py
Requires the dev deps (wntr, numpy); it is never imported by the running app.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Reuse the vetted DHALSIM/WNTR simulation from the dataset generator.
sys.path.insert(0, str(HERE.parent / "datasets" / "lab"))
from generate_datasets import STEP_SECONDS, SURGE_START_HOUR, simulate  # noqa: E402

FIELDS = [
    "iteration", "timestamp", "tank_level", "pump1_flow", "pump2_flow",
    "pump1_status", "pump2_status", "tank_inflow", "total_demand",
    "pressure_J39", "pressure_J156", "pressure_J280",
]


def _rows_to_cols(rows) -> dict:
    return {f: [getattr(r, f) for r in rows] for f in FIELDS}


def main() -> None:
    out = HERE / "data" / "trajectory.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    normal = simulate(surge=False)
    surge = simulate(surge=True)

    doc = {
        "step_seconds": STEP_SECONDS,
        "surge_start_iteration": SURGE_START_HOUR * 3600 // STEP_SECONDS,
        "tank_max_level": 6.5,
        "fields": FIELDS,
        "conditions": {
            "normal": _rows_to_cols(normal),
            "surge": _rows_to_cols(surge),
        },
    }
    with out.open("w") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"wrote {out}  steps/condition={len(normal)}  "
          f"true_tank_min(surge)={min(r.tank_level for r in surge):.2f} m")


if __name__ == "__main__":
    main()
