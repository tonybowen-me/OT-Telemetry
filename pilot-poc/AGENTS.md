# AGENTS — pilot-poc

Guidance for automated agents and contributors working in `pilot-poc/`.

## What this is

A deterministic demo: PILOT (causal telemetry integrity, Layers 1-3) vs a Sigma
correlational baseline, evaluated on pre-recorded DHALSIM `minitown` datasets.

## Ground rules

- **Determinism, no ML.** The reasoning path (Layers 1-3, Sigma) must stay
  rule-based and explainable. Do not introduce ML/statistical models into it.
- **PILOT sees only `reported.csv`.** Never feed ground truth into the engines;
  it exists only for the UI ("actual vs reported") and tests.
- **Keep the lab separate.** `datasets/lab/` (needs `wntr`/`numpy`) is offline. The
  deployed app must never import it or require a simulator at runtime.
- **All thresholds in `app/config.py`.** No magic numbers scattered in engines.
- **Terminology.** Use scenario / valid / violation / uncertain / operational
  finding. PILOT is *not* anomaly detection; don't relabel it as such.

## Layout

```
app/            FastAPI app + engines (runtime; deps = requirements.txt)
  engines/      layer1, layer2, layer3, sigma, comparison
datasets/       committed scenario data (ground_truth.csv, reported.csv, meta.yaml)
  lab/          offline generator (deps = requirements-dev.txt)
docs/           SPEC, RULES, DEPLOYMENT
tests/          pytest (ingestion, per-layer, end-to-end)
```

## Dev workflow

```bash
pip install -r requirements-dev.txt
pytest                        # must stay green
uvicorn app.main:app --reload
python -m pyflakes app tests  # lint
```

If you change scenarios, regenerate data (`python datasets/lab/generate_datasets.py`)
and keep each scenario's `meta.yaml` `expected_pilot` / `expected_sigma` in sync —
`tests/test_end_to_end.py` asserts the computed outcome matches the declared one.
