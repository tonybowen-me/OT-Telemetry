"""FastAPI entrypoint for the PILOT app (application #2 of 2).

PILOT is a separate service from the DHALSIM water utility. It has two modes:

  * LIVE  -- subscribe to the running utility's SCADA feed (``LAB_URL``) and
             validate it continuously (``/`` and ``/api/live``).
  * RECORDED -- replay the four pre-baked DHALSIM scenarios from disk, for a
             deterministic offline demo / tests (``/recorded`` and
             ``/api/scenario/...``).

Stateless either way: no database, and no simulator in-process -- so it deploys
on a free tier. The heavy hydraulics live in the separate lab service.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import ingestion, live
from .engines import comparison
from .models import EvaluationResult

app = FastAPI(title="PILOT x DHALSIM - OT Telemetry Integrity Demo", version="2.0.0")

WEB_DIR = Path(__file__).resolve().parent / "web"


@app.get("/api/live", response_model=EvaluationResult)
def live_eval() -> EvaluationResult:
    try:
        return live.evaluate_live()
    except live.LabUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/lab-status")
def lab_status() -> dict:
    try:
        return {"connected": True, "lab_url": live.LAB_URL, "status": live.lab_status()}
    except live.LabUnavailable as exc:
        return {"connected": False, "lab_url": live.LAB_URL, "error": str(exc)}


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
    return {"status": "ok", "scenarios": ingestion.list_scenarios(), "lab_url": live.LAB_URL}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (WEB_DIR / "templates" / "live.html").read_text()


@app.get("/recorded", response_class=HTMLResponse)
def recorded() -> str:
    return (WEB_DIR / "templates" / "index.html").read_text()


app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
