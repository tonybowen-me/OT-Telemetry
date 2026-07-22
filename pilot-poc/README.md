# PILOT × DHALSIM — OT Telemetry Integrity Demo

A deployable demonstration that **reported OT telemetry cannot be trusted on its
own**, and that a *causal* integrity layer (PILOT) catches falsified telemetry
that a *correlational* baseline (Sigma-style threshold rules) misses.

The physical data comes from a **standalone, third-party water-distribution lab**
— the [DHALSIM](https://github.com/Critical-Infrastructure-Systems-Lab/DHALSIM)
`minitown` topology, simulated with EPANET/WNTR (the exact engine DHALSIM wraps).
The lab is deliberately **separate** from the web app: it runs offline and records
datasets; the app only ingests them. That keeps the deployable service tiny and
free-tier friendly (no Mininet, no root, no simulator at runtime).

## What it proves

| Scenario | Class | PILOT | Correlational baseline |
|---|---|---|---|
| Normal operation | valid | **valid** | silent |
| Demand surge (burst main), honest telemetry | operational | **valid** + operational finding | **alerts** (low level/pressure) |
| Concealment MITM freezes the tank-level tag | falsified | **violation** (mass balance) | **silent** — the lie is in-band |
| DoS drops the tank-level tag | incomplete | **uncertain** | silent |

The operational and concealment scenarios are the **same physical event**. The
only difference is whether the telemetry is falsified — which is exactly what
determines whether a correlational tool sees it. PILOT gets both right:
`valid`+finding for the honest event, `violation` for the concealed one.

## Architecture

```
datasets/lab/generate_datasets.py   the LAB: EPANET/WNTR over DHALSIM minitown ->
                                     ground_truth.csv + reported.csv per scenario
        │  (offline, pre-recorded, committed)
        ▼
app/ingestion.py                    load + STEP-normalise + relevance-filter
app/engines/layer1.py               PILOT L1: deterministic invariants (pass/fail/n-a)
app/engines/layer2.py               PILOT L2: residual trust scoring
app/engines/layer3.py               PILOT L3: counterfactual root-cause ranking
app/engines/sigma.py                correlational baseline (thresholds on reported)
app/engines/comparison.py           orchestrates + builds the output contract
app/main.py                         FastAPI + minimal dashboard
```

PILOT only ever sees the **reported** stream. Ground truth is used solely to draw
"actual vs reported" in the UI and to assert against physical truth in tests.

## Run locally

```bash
cd pilot-poc
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

With Docker:

```bash
docker build -t pilot-dhalsim pilot-poc
docker run -p 8000:8000 pilot-dhalsim
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Regenerate the datasets (optional)

The datasets are committed, so you do **not** need this to run the app. To rebuild
them from the DHALSIM topology:

```bash
pip install -r requirements-dev.txt      # pulls in wntr + numpy
python datasets/lab/generate_datasets.py
```

## Deploy on Render (free)

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). `render.yaml` is included; the free
Python web service builds from `requirements.txt` and starts uvicorn.

## Docs

- [docs/SPEC.md](docs/SPEC.md) — scope, scenario classes, output contract.
- [docs/RULES.md](docs/RULES.md) — every invariant / trust score / Sigma rule.
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Render + Docker.
