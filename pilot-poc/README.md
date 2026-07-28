# PILOT × DHALSIM — OT Telemetry Integrity Demo

Two separate, live applications that together prove **reported OT telemetry
cannot be trusted on its own**, and that a *causal* integrity layer (PILOT)
catches falsified telemetry that a *correlational* baseline (Sigma-style
threshold rules) misses.

1. **DHALSIM Water Utility** (`lab/`) — a standalone water-OT process. It streams
   the [DHALSIM](https://github.com/Critical-Infrastructure-Systems-Lab/DHALSIM)
   `minitown` topology live (physics baked from EPANET/WNTR, the exact engine
   DHALSIM wraps), drives its pumps, and publishes a **SCADA feed** plus an
   operator HMI. An attacker console can arm DHALSIM-style network attacks
   (concealment MITM / DoS) on the SCADA link in real time. It knows nothing
   about PILOT.
2. **PILOT** (`app/`) — a *separate* service that subscribes to the utility's
   SCADA feed (and nothing else) and validates it continuously, showing
   `valid` / `violation` / `uncertain` live next to a correlational baseline.

The two apps run as two processes on two ports (and deploy as two Render
services). Open both side by side: arm an attack in the utility and watch its own
HMI stay green while PILOT — seeing only the SCADA feed — flips to `violation`.

Neither app runs a hydraulic simulator or needs Mininet/root at runtime (the
physics are pre-baked into `lab/data/trajectory.json`), so both fit a free tier.

## What it proves

| Utility state (armed in its console) | PILOT | Correlational baseline |
|---|---|---|
| Nominal demand, no attack | **valid** | silent |
| Demand surge (burst main), no attack — honest telemetry | **valid** + operational finding | **alerts** (low level/pressure) |
| Demand surge + concealment MITM (tank-level tag frozen) | **violation** (mass balance) | **silent** — the lie is in-band |
| DoS drops the tank-level tag | **uncertain** | silent |

The surge and the concealment cases are the **same physical event**. The only
difference is whether the telemetry is falsified — which is exactly what
determines whether a correlational tool sees it. PILOT gets both right:
`valid`+finding for the honest event, `violation` for the concealed one.

## Architecture

```
lab/  ── DHALSIM Water Utility (app 1) ──────────────────────────────────────
  build_trajectories.py   offline: EPANET/WNTR over DHALSIM minitown -> trajectory.json
  simulator.py            live clock over the trajectory + attack injection
  service.py              FastAPI: /api/scada (reported), /api/truth, HMI, console
        │  HTTP, SCADA feed only  (never ground truth)
        ▼
app/  ── PILOT (app 2) ───────────────────────────────────────────────────────
  live.py                 subscribe to /api/scada, normalise -> canonical frames
  engines/layer1.py       PILOT L1: deterministic invariants (pass/fail/n-a)
  engines/layer2.py       PILOT L2: residual trust scoring
  engines/layer3.py       PILOT L3: counterfactual root-cause ranking
  engines/sigma.py        correlational baseline (thresholds on reported)
  engines/comparison.py   orchestrates + builds the output contract
  main.py                 FastAPI: live dashboard (/) + recorded scenarios (/recorded)
```

PILOT only ever sees the **reported** SCADA stream. Ground truth is used solely
to draw "actual vs reported" in the UI and to assert against physical truth in
tests. The four fixed scenarios above are also available offline as recorded
datasets (`datasets/`, `/recorded`) for a deterministic, lab-free demo and tests.

## Run locally

Two terminals (or use Docker Compose below):

```bash
cd pilot-poc
pip install -r requirements-dev.txt          # or: lab/requirements.txt + requirements.txt

# terminal 1 — the water utility (app 1)
uvicorn lab.service:app --port 8001           # HMI at http://127.0.0.1:8001

# terminal 2 — PILOT (app 2), pointed at the utility
LAB_URL=http://localhost:8001 uvicorn app.main:app --port 8002   # http://127.0.0.1:8002
```

Open PILOT (8002) and the utility HMI (8001) side by side. In the utility console
arm **Demand surge**, then **Concealment MITM**, and watch PILOT flip to
`violation` while the HMI stays green.

### With Docker Compose

```bash
cd pilot-poc
docker compose up --build
# utility -> http://localhost:8001 , pilot -> http://localhost:8002
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Regenerate the physics (optional)

The baked trajectory and recorded datasets are committed, so you do **not** need
this to run the apps. To rebuild them from the DHALSIM topology:

```bash
pip install -r requirements-dev.txt      # pulls in wntr + numpy
python lab/build_trajectories.py         # -> lab/data/trajectory.json (live utility)
python datasets/lab/generate_datasets.py # -> datasets/<scenario>/ (recorded demo)
```

## Deploy on Render (free)

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). `render.yaml` defines **two** free
web services (utility + PILOT); PILOT's `LAB_URL` is wired to the utility.

## Docs

- [docs/SPEC.md](docs/SPEC.md) — scope, two-app architecture, scenario classes, output contract.
- [docs/RULES.md](docs/RULES.md) — every invariant / trust score / Sigma rule.
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Render + Docker Compose.
