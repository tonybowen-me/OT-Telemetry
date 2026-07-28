"""Live SCADA ingestion: pull the DHALSIM utility's feed and evaluate it.

PILOT (application #2) treats the utility (application #1) as an untrusted black
box reachable over HTTP. It fetches ONLY the SCADA feed (``/api/scada``) -- never
the utility's physical ground truth -- normalises it into canonical frames, and
runs the same deterministic engines used for recorded scenarios.

The ground-truth series is fetched separately purely so the dashboard can draw
"actual vs reported"; it is passed to the evaluator as evidence, not to the
engines.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from .models import EvaluationResult, Frame
from .engines import comparison

def _normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    # Render's `fromService` host property yields a bare hostname; assume https.
    if url and "://" not in url:
        url = "https://" + url
    return url


LAB_URL = _normalize_url(os.environ.get("LAB_URL", "http://localhost:8001"))
LIVE_WINDOW = int(os.environ.get("LIVE_WINDOW", "48"))

_FRAME_FIELDS = set(Frame.model_fields.keys())


class LabUnavailable(RuntimeError):
    """Raised when the DHALSIM utility feed cannot be reached."""


def _get(path: str) -> dict:
    url = f"{LAB_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=4) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise LabUnavailable(f"cannot reach DHALSIM utility at {url}: {e}") from e


def _to_frame(raw: dict) -> Frame:
    data = {k: v for k, v in raw.items() if k in _FRAME_FIELDS}
    data.setdefault("attack_flag", 0)
    data.setdefault("missing", 0)
    if data.get("attack_flag") is None:
        data["attack_flag"] = 0
    if data.get("missing") is None:
        data["missing"] = 0
    return Frame(**data)


def _scenario_name(status: dict) -> str:
    cond = "demand surge" if status.get("condition") == "surge" else "nominal demand"
    atk = status.get("attack", "none")
    if atk == "none":
        return f"Live SCADA feed \u2014 {cond}, no attack"
    label = {"concealment_mitm": "concealment MITM", "dos": "DoS"}.get(atk, atk)
    return f"Live SCADA feed \u2014 {cond}, {label} armed"


def evaluate_live(window: Optional[int] = None) -> EvaluationResult:
    n = window or LIVE_WINDOW
    scada = _get(f"/api/scada?window={n}")
    truth = _get(f"/api/truth?window={n}")
    status = scada.get("status", {})

    reported = [_to_frame(f) for f in scada.get("frames", [])]
    ground_truth = [_to_frame(f) for f in truth.get("frames", [])]

    result = comparison.evaluate_frames(
        reported, ground_truth,
        scenario_id="live",
        scenario_name=_scenario_name(status),
    )
    return result


def lab_status() -> dict:
    return _get("/api/status")
