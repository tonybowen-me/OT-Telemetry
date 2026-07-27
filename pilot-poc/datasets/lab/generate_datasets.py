#!/usr/bin/env python3
"""
Standalone DHALSIM lab -> PILOT dataset generator.

This is the *lab*. It is deliberately separate from the demo web app: it runs a
water-distribution hydraulic simulation and writes recorded telemetry that the
PILOT demo later ingests. Nothing in the deployed web app depends on this file,
so the app can run for free on a tiny host while the heavy simulation stays here.

Physics
-------
The topology, control logic and hydraulic engine are taken directly from the
third-party DHALSIM project
(https://github.com/Critical-Infrastructure-Systems-Lab/DHALSIM):

  * topology + controls : examples/minitown_topology/minitown_map.inp  (bundled here)
  * hydraulic engine     : EPANET, via WNTR 1.2.0 (the exact engine DHALSIM wraps)

DHALSIM's own physical process runs EPANET/WNTR over this .inp and writes a
``ground_truth.csv``. We reproduce that here and then derive a ``reported.csv``
that reflects what SCADA / a correlational tool would see after a DHALSIM-style
network attack has manipulated the telemetry on the wire:

  * ground_truth.csv : the true physical state (never visible to an attacker)
  * reported.csv     : the post-manipulation view (what SCADA / Sigma see)

Scenarios (mapped to the four PILOT scenario classes in the reference docs):

  normal                     valid            honest telemetry, nominal demand
  operational_demand_surge   operational      real demand surge, HONEST telemetry
  concealment_mitm           falsified        SAME demand surge, but the tank level
                                              tag is frozen on the wire so SCADA never
                                              sees the tank draining (DHALSIM
                                              concealment_mitm)
  dos_incomplete             incomplete       DoS drops the tank-level tag for a window

The operational and concealment scenarios share the *same physical event*; the only
difference is whether the telemetry is falsified. That is the whole point: a
correlational baseline catches the honest event and misses the concealed one, while
PILOT catches both correctly (violation vs valid+finding).

Run:  python3 generate_datasets.py [--out <dir>]
"""
from __future__ import annotations

import argparse
import copy
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import wntr
import yaml

HERE = Path(__file__).resolve().parent
INP_FILE = HERE / "minitown_map.inp"

# --- Minitown constants (from the DHALSIM topology / control section) ----------
TANK_ID = "TANK"
TANK_INFLOW_PIPE = "P15"          # pipe feeding the tank; its flow == net tank inflow
PUMP1, PUMP2 = "PUMP1", "PUMP2"
PRESSURE_JUNCTIONS = ["J39", "J156", "J280"]

STEP_SECONDS = 300                # report period
HORIZON_HOURS = 6
SURGE_START_HOUR = 2              # demand surge / attack begins here
SURGE_FACTOR = 3.0
CONCEAL_LEVEL = 3.0               # frozen reported level during concealment MITM


def tank_area(wn) -> float:
    d = wn.get_node(TANK_ID).diameter
    return math.pi * (d / 2.0) ** 2


def build_model(surge: bool):
    wn = wntr.network.WaterNetworkModel(str(INP_FILE))
    wn.options.time.duration = HORIZON_HOURS * 3600
    wn.options.time.hydraulic_timestep = STEP_SECONDS
    wn.options.time.report_timestep = STEP_SECONDS
    wn.options.time.pattern_timestep = 3600
    if surge:
        # Scale every demand pattern from SURGE_START_HOUR onward (a burst main /
        # sustained over-draw). Honest physics; the tank draws down hard.
        start_idx = SURGE_START_HOUR
        for pname in wn.pattern_name_list:
            pat = wn.get_pattern(pname)
            mult = list(pat.multipliers)
            for i in range(len(mult)):
                if i >= start_idx:
                    mult[i] *= SURGE_FACTOR
            pat.multipliers = mult
    return wn


@dataclass
class Row:
    iteration: int
    timestamp: int
    tank_level: float
    pump1_flow: float
    pump2_flow: float
    pump1_status: int
    pump2_status: int
    tank_inflow: float
    total_demand: float
    pressure_J39: float
    pressure_J156: float
    pressure_J280: float
    attack_flag: int = 0
    missing: int = 0


def simulate(surge: bool) -> list[Row]:
    wn = build_model(surge)
    res = wntr.sim.EpanetSimulator(wn).run_sim()
    elev = wn.get_node(TANK_ID).elevation
    times = list(res.node["head"].index)
    rows: list[Row] = []
    for i, t in enumerate(times):
        if t % STEP_SECONDS != 0:
            continue
        lvl = float(res.node["head"][TANK_ID][t]) - elev
        q1 = float(res.link["flowrate"][PUMP1][t])
        q2 = float(res.link["flowrate"][PUMP2][t])
        s1 = float(res.link["status"][PUMP1][t])
        s2 = float(res.link["status"][PUMP2][t])
        qin = float(res.link["flowrate"][TANK_INFLOW_PIPE][t])
        dem = sum(float(res.node["demand"][j][t]) for j in wn.junction_name_list) * 1000.0
        rows.append(Row(
            iteration=int(t // STEP_SECONDS), timestamp=int(t),
            tank_level=round(max(0.0, lvl), 4),
            pump1_flow=round(q1, 4), pump2_flow=round(q2, 4),
            pump1_status=int(round(s1)), pump2_status=int(round(s2)),
            tank_inflow=round(qin, 4), total_demand=round(dem, 4),
            pressure_J39=round(float(res.node["pressure"]["J39"][t]), 3),
            pressure_J156=round(float(res.node["pressure"]["J156"][t]), 3),
            pressure_J280=round(float(res.node["pressure"]["J280"][t]), 3),
        ))
    return rows


def make_reported(gt: list[Row], attack: str) -> list[Row]:
    """Derive the SCADA-visible view from ground truth for a given attack."""
    rep = [copy.copy(r) for r in gt]
    start = SURGE_START_HOUR * 3600 // STEP_SECONDS
    if attack == "concealment_mitm":
        # Nominal snapshot the attacker replays for the concealed tank subsystem
        # (DHALSIM concealment_mitm feeds coherent replayed/AE-generated values so
        # SCADA sees a normal picture). Level + its pressure sensors are faked to
        # a pre-attack nominal; the independent tank-inflow flow meter (a different
        # measurement the attacker did not compromise) stays truthful and betrays
        # the lie to PILOT.
        nominal = gt[start - 1]
        for r in rep:
            if r.iteration >= start:
                r.tank_level = CONCEAL_LEVEL
                r.pressure_J39 = nominal.pressure_J39
                r.pressure_J156 = nominal.pressure_J156
                r.pressure_J280 = nominal.pressure_J280
                r.attack_flag = 1
    elif attack == "dos":
        for r in rep:
            if start <= r.iteration < (SURGE_START_HOUR + 3) * 3600 // STEP_SECONDS:
                r.tank_level = float("nan")
                r.tank_inflow = float("nan")
                r.missing = 1
                r.attack_flag = 1
    return rep


FIELDS = [
    "iteration", "timestamp", "tank_level", "pump1_flow", "pump2_flow",
    "pump1_status", "pump2_status", "tank_inflow", "total_demand",
    "pressure_J39", "pressure_J156", "pressure_J280", "attack_flag", "missing",
]


def _fmt(v):
    if isinstance(v, float) and math.isnan(v):
        return ""
    return v


def write_csv(rows: list[Row], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for r in rows:
            w.writerow([_fmt(getattr(r, k)) for k in FIELDS])


SCENARIOS = {
    "normal": {
        "surge": False, "attack": "none",
        "meta": {
            "name": "Normal operation",
            "class": "valid",
            "description": "Minitown runs under nominal demand with honest telemetry.",
            "attack": None,
            "expected_pilot": "valid",
            "expected_sigma": "no_alert",
            "narrative": "Baseline. Reported telemetry matches physical reality; every "
                         "PILOT invariant holds and the correlational baseline stays quiet.",
        },
    },
    "operational_demand_surge": {
        "surge": True, "attack": "none",
        "meta": {
            "name": "Operational issue (demand surge / burst main)",
            "class": "operational_issue",
            "description": "A large HONEST demand surge from hour 2 draws the tank down and "
                           "depresses downstream pressure. No telemetry is falsified.",
            "attack": None,
            "expected_pilot": "valid",
            "expected_sigma": "alert",
            "narrative": "A genuine physical event with honest telemetry. Correlational rules "
                         "alert on the low tank level / low pressure. PILOT confirms the state "
                         "is physically consistent (valid) and raises a separate operational "
                         "finding -- it is not a falsified-data violation.",
        },
    },
    "concealment_mitm": {
        "surge": True, "attack": "concealment_mitm",
        "meta": {
            "name": "Falsified telemetry (concealment MITM on tank level)",
            "class": "falsified_telemetry",
            "description": "The SAME demand surge as the operational scenario, but a DHALSIM "
                           "concealment_mitm freezes the reported TANK level at 3.0 m on the "
                           "wire. SCADA never sees the tank draining toward empty.",
            "attack": {"type": "concealment_mitm", "target": "PLC1", "tag": "TANK",
                       "start_hour": SURGE_START_HOUR, "conceal_level": CONCEAL_LEVEL},
            "expected_pilot": "violation",
            "expected_sigma": "no_alert",
            "narrative": "The money shot. Reported tank level is flat and in-band, so the Sigma "
                         "rules never fire even though the real tank is emptying. PILOT compares "
                         "the reported level against the change implied by tank inflow and demand "
                         "(mass balance) and against the still-truthful pressures, and flags a "
                         "causal violation: a flat level is impossible while the network keeps "
                         "drawing water.",
        },
    },
    "dos_incomplete": {
        "surge": False, "attack": "dos",
        "meta": {
            "name": "Incomplete data (DoS on level sensor)",
            "class": "incomplete_data",
            "description": "A DoS on PLC1 drops the tank-level tag for a 3-hour window under "
                           "otherwise nominal conditions; the value required to resolve tank "
                           "state is missing.",
            "attack": {"type": "dos", "target": "PLC1", "tag": "TANK",
                       "start_hour": SURGE_START_HOUR, "duration_hours": 3},
            "expected_pilot": "uncertain",
            "expected_sigma": "no_alert",
            "narrative": "Required telemetry is missing. PILOT refuses to guess and returns "
                         "uncertain for the affected window rather than asserting valid or "
                         "violation.",
        },
    },
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE.parent), help="datasets/ root directory")
    args = ap.parse_args()
    out_root = Path(args.out)

    # ground truth per physical condition is shared; cache the two runs.
    gt_cache: dict[bool, list[Row]] = {}
    for key, spec in SCENARIOS.items():
        surge = spec["surge"]
        if surge not in gt_cache:
            gt_cache[surge] = simulate(surge)
        gt = [copy.copy(r) for r in gt_cache[surge]]
        rep = make_reported(gt, spec["attack"])

        d = out_root / key
        d.mkdir(parents=True, exist_ok=True)
        write_csv(gt, d / "ground_truth.csv")
        write_csv(rep, d / "reported.csv")
        meta = dict(spec["meta"])
        meta["id"] = key
        meta["step_seconds"] = STEP_SECONDS
        meta["steps"] = len(gt)
        meta["tank_max_level"] = 6.5
        with (d / "meta.yaml").open("w") as f:
            yaml.safe_dump(meta, f, sort_keys=False)
        gmin = min(r.tank_level for r in gt)
        print(f"[{key}] steps={len(gt)} true_tank_min={gmin:.2f} surge={surge} attack={spec['attack']} -> {d}")


if __name__ == "__main__":
    main()
