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

- No live DHALSIM/Mininet/MiniCPS at runtime (the lab is offline/pre-recorded).
- No ML in the reasoning path — everything is deterministic and auditable.
- No real plant/customer telemetry; no database, auth, or multi-tenancy.

## The lab (separate from the app)

`datasets/lab/generate_datasets.py` runs the DHALSIM `minitown` topology through
EPANET/WNTR and writes, per scenario:

- `ground_truth.csv` — true physical state (never visible to an attacker).
- `reported.csv` — what SCADA / a correlational tool sees after a DHALSIM-style
  network attack manipulates telemetry on the wire.
- `meta.yaml` — scenario metadata + declared expected outcomes.

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
