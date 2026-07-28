# SPEC — PILOT × DHALSIM demo

## Goal

Prove the reference-doc thesis on data from an independent OT lab:

- Reported telemetry can be **falsified**.
- **Correlation-based** detection can miss or understate falsified telemetry.
- **PILOT** identifies causal / physical inconsistency.
- The system distinguishes **valid**, **operational** issues, **causal violations**,
  and **uncertainty** from incomplete data.
- Findings are explained in human-readable language.

## Non-goals

- No Mininet/MiniCPS at runtime (that layer needs root; not free-tier friendly).
  The hydraulics are pre-baked from EPANET/WNTR; nothing solves hydraulics live.
- No ML in the reasoning path — everything is deterministic and auditable.
- No real plant/customer telemetry; no database, auth, or multi-tenancy.

## Two-app architecture

The demo is two independent services:

1. **DHALSIM Water Utility** (`lab/`) — a standalone OT process. `build_trajectories.py`
   bakes the DHALSIM `minitown` physics (EPANET/WNTR) into `data/trajectory.json`;
   `simulator.py` streams it on a live clock and applies DHALSIM-style attacks
   (concealment MITM / DoS) to the SCADA-visible view; `service.py` exposes the
   SCADA feed (`/api/scada`) and an operator HMI + attacker console. It has no
   knowledge of PILOT.
2. **PILOT** (`app/`) — a separate service. `live.py` subscribes to the utility's
   SCADA feed (only), normalises it to canonical frames, and the engines validate
   it live. It reaches the utility over HTTP only; the utility never imports PILOT.

The utility publishes `/api/truth` (physical ground truth) purely for its own HMI
overlay — PILOT never fetches it into the engines.

## The offline lab (recorded scenarios)

For a deterministic, lab-free demo and for tests, `datasets/lab/generate_datasets.py`
runs the same DHALSIM `minitown` topology through EPANET/WNTR and writes, per
scenario:

- `ground_truth.csv` — true physical state (never visible to an attacker).
- `reported.csv` — what SCADA / a correlational tool sees after a DHALSIM-style
  network attack manipulates telemetry on the wire.
- `meta.yaml` — scenario metadata + declared expected outcomes.

These back PILOT's `/recorded` view; the live path (`/`) uses the utility instead.

## Three telemetry views (kept distinct)

- **baseline** — nominal expected behaviour (encoded in the physical model / thresholds).
- **actual** — ground truth from the lab.
- **reported** — post-manipulation SCADA view; the *only* thing PILOT consumes.

## Scenario classes

| id | class | physical event | telemetry | expected PILOT | expected Sigma |
|---|---|---|---|---|---|
| `normal` | valid | nominal | honest | valid | no alert |
| `operational_demand_surge` | operational | burst / over-draw | honest | valid + finding | alert |
| `concealment_mitm` | falsified | same over-draw | level tag frozen | violation | no alert |
| `dos_incomplete` | incomplete | nominal | level tag dropped | uncertain | no alert |

## Decision order (PILOT status)

1. If a required tag is missing for a sustained window → **uncertain**.
2. Else if any hard invariant fails → **violation**.
3. Else → **valid** (operational findings are reported separately and never change
   the integrity verdict).

## Output contract (`EvaluationResult`)

- `scenario_id`, `scenario_name`, `scenario_class`
- `pilot_status` ∈ {valid, violation, uncertain}
- `operational_findings[]` — process-health observations, distinct from integrity
- `layer1` / `layer2` / `layer3` — per-layer detail with evidence
- `sigma` — `alert`, `highest_level`, `triggered_rules[]`
- `explanations[]` — human-readable
- `evidence{}` — actual vs reported series + first-violation markers
- `comparison` — why PILOT and the baseline differ
- `timesteps`
