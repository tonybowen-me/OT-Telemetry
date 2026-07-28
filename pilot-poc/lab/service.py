"""DHALSIM Water Utility -- the OT lab (application #1).

A standalone, continuously-running Minitown SCADA process with an operator HMI
and an attacker console. It has no knowledge of PILOT. The only data it exposes
to the outside world is its SCADA feed (``/api/scada``) -- exactly what a real
historian/SCADA server would offer. ``/api/truth`` is the utility's own physical
ground truth, used only by its HMI overlay (and never by PILOT).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .simulator import Utility

HERE = Path(__file__).resolve().parent
STATIC = HERE / "web" / "static"
TEMPLATES = HERE / "web" / "templates"

app = FastAPI(title="DHALSIM Water Utility (Minitown SCADA)")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

utility = Utility()


@app.on_event("startup")
def _startup() -> None:
    utility.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    utility.stop()


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", **utility.status()}


@app.get("/api/status")
def status() -> dict:
    return utility.status()


@app.get("/api/scada")
def scada(window: int = Query(1, ge=1, le=96)) -> dict:
    """The SCADA-visible telemetry feed (post-attack). This is all PILOT sees."""
    return {"status": utility.status(), "frames": utility.scada_window(window)}


@app.get("/api/truth")
def truth(window: int = Query(1, ge=1, le=96)) -> dict:
    """Physical ground truth -- utility HMI overlay only, never sent to PILOT."""
    return {"status": utility.status(), "frames": utility.truth_window(window)}


@app.post("/api/condition/{condition}")
def set_condition(condition: str) -> dict:
    try:
        utility.set_condition(condition)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return utility.status()


@app.post("/api/attack/{attack}")
def set_attack(attack: str) -> dict:
    try:
        utility.set_attack(attack)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return utility.status()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (TEMPLATES / "index.html").read_text()
