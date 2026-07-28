# AGENTS — pilot-poc

Guidance for automated agents and contributors working in `pilot-poc/`.

## What this is

Two separate apps: a **DHALSIM water utility** (`lab/`) that streams the
`minitown` process live and publishes a SCADA feed, and **PILOT** (`app/`) that
validates that feed live (causal telemetry integrity, Layers 1-3) next to a Sigma
correlational baseline. The same engines also run over four pre-recorded
scenarios for a lab-free offline demo and tests.

## Ground rules

- **Two apps, one direction.** The utility (`lab/`) never imports `app/`. PILOT
  reaches the utility only over HTTP, via the SCADA feed (`/api/scada`).
- **PILOT sees only reported telemetry.** Never feed ground truth into the
  engines — not the utility's `/api/truth`, not `ground_truth.csv`. Ground truth
  exists only for the UI ("actual vs reported") and tests.
- **Determinism, no ML.** The reasoning path (Layers 1-3, Sigma) must stay
  rule-based and explainable. Do not introduce ML/statistical models into it.
- **Keep the simulator offline.** `datasets/lab/generate_datasets.py` and
  `lab/build_trajectories.py` need `wntr`/`numpy`; they run offline only. Neither
  deployed service imports them or runs a simulator at runtime.
- **All thresholds in `app/config.py`.** No magic numbers scattered in engines.
- **Terminology.** Use scenario / valid / violation / uncertain / operational
  finding. PILOT is *not* anomaly detection; don't relabel it as such.

## Layout

```
lab/            DHALSIM water utility service (deps = lab/requirements.txt)
  build_trajectories.py  offline: EPANET/WNTR -> data/trajectory.json (dev deps)
  simulator.py           live clock + DHALSIM-style attack injection
  service.py             FastAPI: SCADA feed + HMI/attacker console
app/            PILOT service + engines (deps = requirements.txt)
  live.py       SCADA-feed client -> canonical frames
  engines/      layer1, layer2, layer3, sigma, comparison
datasets/       committed recorded scenarios (ground_truth.csv, reported.csv, meta.yaml)
  lab/          offline dataset generator (deps = requirements-dev.txt)
docs/           SPEC, RULES, DEPLOYMENT
tests/          pytest (ingestion, per-layer, end-to-end, live)
```

## Dev workflow

```bash
pip install -r requirements-dev.txt
pytest                              # must stay green
python -m pyflakes app lab tests datasets/lab/generate_datasets.py  # lint

# run both apps
uvicorn lab.service:app --port 8001
LAB_URL=http://localhost:8001 uvicorn app.main:app --port 8002
```

If you change the live physics, rebuild `lab/data/trajectory.json`
(`python lab/build_trajectories.py`). If you change the recorded scenarios,
regenerate them (`python datasets/lab/generate_datasets.py`) and keep each
`meta.yaml` `expected_pilot` / `expected_sigma` in sync — `tests/test_end_to_end.py`
asserts the computed outcome matches the declared one.
