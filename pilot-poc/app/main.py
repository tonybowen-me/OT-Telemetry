"""FastAPI entrypoint for the PILOT DHALSIM demo.

Stateless: it loads pre-recorded DHALSIM-derived datasets from disk and runs the
PILOT (Layer 1-3) + Sigma evaluation on demand. No database, no simulator at
runtime -- so it deploys on a free tier.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import ingestion
from .engines import comparison
from .models import EvaluationResult

app = FastAPI(title="PILOT x DHALSIM - OT Telemetry Integrity Demo", version="1.0.0")

WEB_DIR = Path(__file__).resolve().parent / "web"


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    out = []
    for sid in ingestion.list_scenarios():
        meta = ingestion.load_scenario(sid).meta
        out.append({
            "id": meta.id,
            "name": meta.name,
            "scenario_class": meta.scenario_class,
            "description": meta.description,
            "expected_pilot": meta.expected_pilot,
            "expected_sigma": meta.expected_sigma,
        })
    return out


@app.get("/api/scenario/{scenario_id}", response_model=EvaluationResult)
def evaluate(scenario_id: str) -> EvaluationResult:
    try:
        scenario = ingestion.load_scenario(scenario_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return comparison.evaluate_scenario(scenario)


@app.get("/api/scenario/{scenario_id}/meta")
def scenario_meta(scenario_id: str) -> dict:
    try:
        meta = ingestion.load_scenario(scenario_id).meta
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return meta.model_dump()


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "scenarios": ingestion.list_scenarios()}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (WEB_DIR / "templates" / "index.html").read_text()


app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
