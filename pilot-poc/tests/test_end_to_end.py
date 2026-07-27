import pytest
from fastapi.testclient import TestClient

from app import ingestion
from app.engines import comparison
from app.main import app

client = TestClient(app)

EXPECTED = {
    "normal": ("valid", False),
    "operational_demand_surge": ("valid", True),
    "concealment_mitm": ("violation", False),
    "dos_incomplete": ("uncertain", False),
}


@pytest.mark.parametrize("sid,expected", EXPECTED.items())
def test_scenario_outcomes_match_ground_truth_intent(sid, expected):
    exp_pilot, exp_sigma_alert = expected
    result = comparison.evaluate_scenario(ingestion.load_scenario(sid))
    assert result.pilot_status == exp_pilot
    assert result.sigma.alert is exp_sigma_alert
    # meta's declared expectation must agree with the computed one
    meta = ingestion.load_scenario(sid).meta
    assert meta.expected_pilot == exp_pilot


def test_output_contract_shape():
    r = comparison.evaluate_scenario(ingestion.load_scenario("concealment_mitm"))
    assert r.scenario_name and r.scenario_class
    assert r.explanations
    assert r.comparison
    for key in ("iterations", "reported_tank_level", "actual_tank_level"):
        assert key in r.evidence
    assert r.timesteps == len(r.evidence["iterations"])


def test_falsified_diverges_from_truth_but_operational_matches():
    conceal = ingestion.load_scenario("concealment_mitm")
    # reported level is frozen while true level drains -> they must diverge
    rep = [f.tank_level for f in conceal.reported]
    gt = [f.tank_level for f in conceal.ground_truth]
    assert max(abs(a - b) for a, b in zip(rep, gt) if a is not None and b is not None) > 1.0

    op = ingestion.load_scenario("operational_demand_surge")
    # honest scenario: reported == ground truth
    for a, b in zip(op.reported, op.ground_truth):
        assert a.tank_level == b.tank_level


def test_api_endpoints():
    assert client.get("/healthz").status_code == 200
    assert len(client.get("/api/scenarios").json()) == 4
    r = client.get("/api/scenario/concealment_mitm")
    assert r.status_code == 200
    assert r.json()["pilot_status"] == "violation"
    assert client.get("/api/scenario/nope").status_code == 404
    assert client.get("/").status_code == 200
