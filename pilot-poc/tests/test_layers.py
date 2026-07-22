from app import ingestion
from app.engines import layer1, layer2, layer3, sigma


def _frames(sid):
    return ingestion.load_scenario(sid).reported


# --- Layer 1 -----------------------------------------------------------------
def test_layer1_normal_all_pass():
    l1 = layer1.evaluate(_frames("normal"))
    assert l1.verdict == "pass"
    assert not l1.violations


def test_layer1_concealment_mass_balance_fails():
    l1 = layer1.evaluate(_frames("concealment_mitm"))
    assert l1.verdict == "fail"
    assert "TANK_MASS_BALANCE" in l1.violations
    mb = next(r for r in l1.invariants if r.rule_id == "TANK_MASS_BALANCE")
    assert mb.status == "fail"
    assert mb.first_violation_iteration is not None


def test_layer1_dos_is_uncertain_not_violation():
    l1 = layer1.evaluate(_frames("dos_incomplete"))
    assert l1.verdict == "uncertain"
    assert not l1.violations  # missing data must not masquerade as a violation
    ins = next(r for r in l1.invariants if r.rule_id == "INSUFFICIENT_DATA")
    assert ins.status == "fail"


def test_layer1_operational_is_valid():
    l1 = layer1.evaluate(_frames("operational_demand_surge"))
    assert l1.verdict == "pass"  # honest telemetry stays physically consistent


# --- Layer 2 -----------------------------------------------------------------
def test_layer2_trust_collapses_on_falsified_level():
    l2 = layer2.evaluate(_frames("concealment_mitm"))
    assert l2.verdict == "fail"
    assert l2.escalate
    level = next(s for s in l2.sensors if s.tag == "TANK.level")
    assert level.min_trust < 0.5


def test_layer2_normal_high_trust():
    l2 = layer2.evaluate(_frames("normal"))
    assert l2.verdict == "pass"
    assert not l2.escalate


# --- Layer 3 -----------------------------------------------------------------
def test_layer3_identifies_sensor_spoof():
    frames = _frames("concealment_mitm")
    l1 = layer1.evaluate(frames)
    l2 = layer2.evaluate(frames)
    l3 = layer3.evaluate(frames, l1, l2)
    assert l3.triggered
    assert l3.top_hypothesis == "sensor_spoof_level"
    assert l3.top_confidence >= 0.5


def test_layer3_not_engaged_when_clean():
    frames = _frames("normal")
    l1 = layer1.evaluate(frames)
    l2 = layer2.evaluate(frames)
    l3 = layer3.evaluate(frames, l1, l2)
    assert not l3.triggered


def test_layer3_data_loss_hypothesis():
    frames = _frames("dos_incomplete")
    l1 = layer1.evaluate(frames)
    l2 = layer2.evaluate(frames)
    l3 = layer3.evaluate(frames, l1, l2)
    assert l3.top_hypothesis == "data_loss"


# --- Sigma -------------------------------------------------------------------
def test_sigma_misses_concealment():
    assert sigma.evaluate(_frames("concealment_mitm")).alert is False


def test_sigma_catches_operational():
    s = sigma.evaluate(_frames("operational_demand_surge"))
    assert s.alert is True
    assert s.highest_level == "high"


def test_sigma_quiet_on_normal():
    assert sigma.evaluate(_frames("normal")).alert is False
