#!/usr/bin/env python3
"""Offline: bake the DHALSIM minitown physical process into a compact trajectory.

This runs EPANET/WNTR (the exact hydraulic engine DHALSIM wraps) over the
third-party DHALSIM ``minitown`` topology for the two physical demand conditions
the live lab can be in -- nominal and demand-surge -- and writes them to
``lab/data/trajectory.json``.

The live utility (``lab/service.py``) *streams* this physical process in real
time on a continuous loop and applies network attacks (concealment MITM / DoS) to
the SCADA view. Because it loops forever, the trajectory is built to be a
**seamless periodic steady state**:

  * A short transient is discarded and an integer number of demand periods is kept,
    so the level/flows at the loop wrap are continuous (no teleport on the chart,
    and no spurious mass-balance blip on honest telemetry at the wrap).
  * The surge is a *periodic* burst-main pattern (a few hours of heavy over-draw,
    then recovery) rather than a permanent step. A permanent surge just empties the
    tank and pins it there -- and while the tank sits flat-empty (inflow ~ 0) a
    frozen level sensor is trivially mass-balance-consistent, so concealment would
    intermittently read as VALID. A sustained periodic drawdown keeps real water
    moving every step, so concealment stays a persistent causal violation.

Both conditions are sliced to the *same* indices/length so the utility's stream
index maps cleanly onto either one when the operator flips the demand condition.

Run:  python3 lab/build_trajectories.py
Requires the dev deps (wntr, numpy); it is never imported by the running app.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import wntr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "datasets" / "lab"))
from generate_datasets import (  # noqa: E402
    INP_FILE, PUMP1, PUMP2, STEP_SECONDS, TANK_ID, TANK_INFLOW_PIPE,
)

FIELDS = [
    "iteration", "timestamp", "tank_level", "pump1_flow", "pump2_flow",
    "pump1_status", "pump2_status", "tank_inflow", "total_demand",
    "pressure_J39", "pressure_J156", "pressure_J280",
]

# --- live physical conditions ------------------------------------------------
# Nominal demand, and a periodic burst-main surge (heavy for SURGE_HIGH_HOURS,
# then light recovery for the rest of each SURGE_PERIOD_HOURS cycle).
HORIZON_HOURS = 60          # long enough to reach periodic steady state
WARMUP_FRACTION = 0.4       # discard this leading transient before extracting
SURGE_PERIOD_HOURS = 6
SURGE_HIGH_HOURS = 2
SURGE_HIGH_FACTOR = 2.5
SURGE_LOW_FACTOR = 0.4


def _multipliers(surge: bool, hours: int) -> "list[float] | None":
    if not surge:
        return None
    out = []
    for h in range(hours + 2):
        phase = h % SURGE_PERIOD_HOURS
        out.append(SURGE_HIGH_FACTOR if phase < SURGE_HIGH_HOURS else SURGE_LOW_FACTOR)
    return out


def simulate(surge: bool) -> list[dict]:
    wn = wntr.network.WaterNetworkModel(str(INP_FILE))
    wn.options.time.duration = HORIZON_HOURS * 3600
    wn.options.time.hydraulic_timestep = STEP_SECONDS
    wn.options.time.report_timestep = STEP_SECONDS
    wn.options.time.pattern_timestep = 3600
    factors = _multipliers(surge, HORIZON_HOURS)
    if factors is not None:
        for pname in wn.pattern_name_list:
            pat = wn.get_pattern(pname)
            base = list(pat.multipliers)[0]
            pat.multipliers = [base * f for f in factors]
    res = wntr.sim.EpanetSimulator(wn).run_sim()
    elev = wn.get_node(TANK_ID).elevation
    times = [t for t in res.node["head"].index if t % STEP_SECONDS == 0]
    rows: list[dict] = []
    for t in times:
        lvl = float(res.node["head"][TANK_ID][t]) - elev
        rows.append({
            "tank_level": round(max(0.0, lvl), 4),
            "pump1_flow": round(float(res.link["flowrate"][PUMP1][t]), 4),
            "pump2_flow": round(float(res.link["flowrate"][PUMP2][t]), 4),
            "pump1_status": int(round(float(res.link["status"][PUMP1][t]))),
            "pump2_status": int(round(float(res.link["status"][PUMP2][t]))),
            "tank_inflow": round(float(res.link["flowrate"][TANK_INFLOW_PIPE][t]), 4),
            "total_demand": round(sum(
                float(res.node["demand"][j][t]) for j in wn.junction_name_list) * 1000.0, 4),
            "pressure_J39": round(float(res.node["pressure"]["J39"][t]), 3),
            "pressure_J156": round(float(res.node["pressure"]["J156"][t]), 3),
            "pressure_J280": round(float(res.node["pressure"]["J280"][t]), 3),
        })
    return rows


def _steady_slice_bounds(n: int) -> tuple[int, int]:
    """Integer number of surge periods from steady state (same for both conditions)."""
    period = SURGE_PERIOD_HOURS * 3600 // STEP_SECONDS
    start = int(n * WARMUP_FRACTION)
    start -= start % period
    span = ((n - start) // period) * period
    return start, span


def _finalize(rows: list[dict], start: int, span: int) -> dict:
    sl = rows[start:start + span]
    cols = {f: [] for f in FIELDS}
    for k, r in enumerate(sl):
        cols["iteration"].append(k)
        cols["timestamp"].append(k * STEP_SECONDS)
        for f in FIELDS[2:]:
            cols[f].append(r[f])
    return cols


def main() -> None:
    out = HERE / "data" / "trajectory.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    normal = simulate(surge=False)
    surge = simulate(surge=True)
    start, span = _steady_slice_bounds(min(len(normal), len(surge)))

    doc = {
        "step_seconds": STEP_SECONDS,
        "tank_max_level": 6.5,
        "fields": FIELDS,
        "conditions": {
            "normal": _finalize(normal, start, span),
            "surge": _finalize(surge, start, span),
        },
    }
    with out.open("w") as f:
        json.dump(doc, f, separators=(",", ":"))
    ncol = doc["conditions"]["normal"]["tank_level"]
    scol = doc["conditions"]["surge"]["tank_level"]
    print(f"wrote {out}  steps/condition={span}  "
          f"normal_lvl[{min(ncol):.2f},{max(ncol):.2f}]  "
          f"surge_lvl[{min(scol):.2f},{max(scol):.2f}]  "
          f"loopgap(surge)={abs(scol[0]-scol[-1]):.3f}")


if __name__ == "__main__":
    main()
