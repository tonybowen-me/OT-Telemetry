from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from simulator import WaterTreatmentPlant, TelemetryFrame
from layer1 import InvariantChecker, Layer1Result
from layer2 import ResidualScorer, Layer2Result
from layer3 import CounterfactualEngine, Layer3Result

plant = WaterTreatmentPlant()
checker = InvariantChecker()
scorer = ResidualScorer()
engine = CounterfactualEngine()

latest_frame: Optional[TelemetryFrame] = None
latest_layer1: Optional[Layer1Result] = None
latest_layer2: Optional[Layer2Result] = None
latest_layer3: Optional[Layer3Result] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_tick_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _tick_loop() -> None:
    global latest_frame, latest_layer1, latest_layer2, latest_layer3
    while True:
        latest_frame = plant.tick()
        latest_layer1 = checker.check(latest_frame)
        latest_layer2 = scorer.score(latest_frame)
        latest_layer3 = engine.evaluate(latest_frame, latest_layer2)
        await asyncio.sleep(1.0)


app = FastAPI(title="Nalco OT Validator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/telemetry")
async def get_telemetry():
    if latest_frame is None:
        raise HTTPException(status_code=503, detail="Simulator not ready")
    return {
        "telemetry": latest_frame,
        "layer1": latest_layer1,
        "layer2": latest_layer2,
        "layer3": latest_layer3,
    }


@app.post("/scenario/{name}")
async def inject_scenario(name: str):
    try:
        plant.inject_anomaly(name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {name!r}")
    return {"status": "ok", "active": name}


@app.delete("/scenario")
async def clear_scenario():
    plant.clear_anomaly()
    return {"status": "ok", "active": None}


@app.post("/mode/{mode}")
async def set_mode(mode: str):
    try:
        plant.set_mode(mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {mode!r}")
    return {"status": "ok", "mode": mode}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
