# DEPLOYMENT

The app is stateless and bundles its datasets, so it deploys on a free tier with
no database and no simulator dependencies.

## Render (free)

`render.yaml` (repo root of `pilot-poc`) defines a free Python web service:

```yaml
services:
  - type: web
    name: pilot-dhalsim-demo
    runtime: python
    plan: free
    rootDir: pilot-poc
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /healthz
```

Steps:

1. Push the repo to GitHub (already the case here).
2. In Render: **New → Blueprint**, point it at the repo. Render reads `render.yaml`.
3. Deploy. The health check hits `/healthz`; the UI is served at `/`.

Notes:
- Only `requirements.txt` is installed on Render — `wntr`/`numpy` (the lab) are in
  `requirements-dev.txt` and are **not** pulled in, keeping the build small.
- Free instances sleep when idle; the first request after a sleep is slow. This is
  fine for a demo.
- `autoDeploy: false` — flip to `true` if you want push-to-deploy.

## Docker (local or any container host)

```bash
docker build -t pilot-dhalsim pilot-poc
docker run -p 8000:8000 pilot-dhalsim
# http://localhost:8000
```

The image installs only runtime deps and copies `app/` + `datasets/`. It honours
`$PORT` if the host sets one (defaults to 8000).

## Endpoints

| path | purpose |
|---|---|
| `/` | dashboard |
| `/api/scenarios` | list scenarios |
| `/api/scenario/{id}` | full evaluation (PILOT + Sigma) |
| `/api/scenario/{id}/meta` | scenario metadata |
| `/healthz` | health check |
