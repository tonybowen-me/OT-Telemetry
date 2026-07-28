# DEPLOYMENT

The demo is **two** stateless services — the DHALSIM water utility and PILOT.
Both bundle their data (the utility streams a pre-baked trajectory; PILOT bundles
the recorded scenarios), so neither needs a database, a simulator, or Mininet/root
at runtime. Both fit a free tier.

## Render (free) — two services

`render.yaml` (in `pilot-poc/`) defines both web services and wires PILOT's
`LAB_URL` to the utility:

```yaml
services:
  - type: web
    name: dhalsim-water-utility
    startCommand: uvicorn lab.service:app --host 0.0.0.0 --port $PORT
    buildCommand: pip install -r lab/requirements.txt
  - type: web
    name: pilot-telemetry-integrity
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    buildCommand: pip install -r requirements.txt
    envVars:
      - key: LAB_URL
        fromService: { type: web, name: dhalsim-water-utility, property: host }
```

Steps:

1. Push the repo to GitHub (already the case here).
2. In Render: **New → Blueprint**, point it at the repo. Render reads `render.yaml`
   and creates both services.
3. Deploy. Each health check hits `/healthz`. Open the PILOT service URL for the
   dashboard and the utility service URL for the HMI.

Notes:
- `LAB_URL` is injected from the utility's `host` (a bare hostname); PILOT prepends
  `https://` automatically.
- Free instances sleep when idle; the first request wakes them (slow), and the
  utility's live clock restarts from zero. Fine for a demo.
- The utility installs only `lab/requirements.txt` (fastapi/uvicorn) — `wntr`/`numpy`
  live in `requirements-dev.txt` and are used only to *rebuild* the trajectory
  offline, so neither deployed build pulls them in.
- `autoDeploy: false` — flip to `true` for push-to-deploy.

## Docker Compose (local or any container host)

```bash
cd pilot-poc
docker compose up --build
# utility -> http://localhost:8001 , pilot -> http://localhost:8002
```

Both services build from the same `Dockerfile`; Compose overrides the command per
service and sets `LAB_URL=http://utility:8001` for PILOT.

## Endpoints

### DHALSIM Water Utility (app 1)

| path | purpose |
|---|---|
| `/` | operator HMI + attacker console |
| `/api/scada?window=N` | SCADA-visible feed (post-attack) — all PILOT consumes |
| `/api/truth?window=N` | physical ground truth (HMI overlay only) |
| `/api/status` | current condition / armed attack / clock |
| `POST /api/condition/{normal\|surge}` | set the physical demand condition |
| `POST /api/attack/{none\|concealment_mitm\|dos}` | arm/clear an attack |
| `/healthz` | health check |

### PILOT (app 2)

| path | purpose |
|---|---|
| `/` | live dashboard (validates the utility's SCADA feed) |
| `/api/live` | live PILOT + Sigma evaluation of the current SCADA window |
| `/api/lab-status` | utility connection + current state |
| `/recorded` | offline dashboard over the four recorded scenarios |
| `/api/scenarios`, `/api/scenario/{id}` | recorded-scenario list + evaluation |
| `/healthz` | health check |
