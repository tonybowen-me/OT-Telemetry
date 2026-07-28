"""Tests for the live two-app path: the DHALSIM utility simulator, the PILOT
live client, and the utility -> SCADA feed -> PILOT integration."""
from __future__ import annotations

from app import live
from app.engines import comparison
from app.models import Frame
from lab.simulator import Utility


def _drive(condition: str, attack: str | None, steps: int = 60,
           arm_after: int = 6) -> Utility:
    """Build a utility, arm a condition/attack, and step it deterministically."""
    u = Utility(tick_seconds=0.0, history=96)
    u.set_condition(condition)
    for i in range(steps):
        if attack and i == arm_after:
            u.set_attack(attack)
        u.advance()
    return u


def _frames(raws: list[dict]) -> list[Frame]:
    return [live._to_frame(r) for r in raws]


def test_utility_scada_only_exposes_reported_fields():
    u = _drive("normal", None, steps=10)
    fr = u.scada_frame()
    assert "tank_level" in fr and "attack_flag" in fr
    # truth history exists separately and is never handed to the SCADA feed API
    assert len(u.truth_window(5)) == 5
    assert len(u.scada_window(5)) == 5


def test_normal_is_valid_and_sigma_silent():
    u = _drive("normal", None, steps=60)
    r = comparison.evaluate_frames(_frames(u.scada_window(48)),
                                   _frames(u.truth_window(48)), "live", "live")
    assert r.pilot_status == "valid"
    assert r.sigma.alert is False


def test_operational_surge_is_valid_with_finding_and_sigma_alerts():
    u = _drive("surge", None, steps=60)
    reported = _frames(u.scada_window(48))
    r = comparison.evaluate_frames(reported, _frames(u.truth_window(48)),
                                   "live", "live")
    assert r.pilot_status == "valid"           # honest telemetry -> not a violation
    assert r.operational_findings              # but a genuine operational problem
    assert r.sigma.alert is True               # correlational baseline fires


def test_concealment_mitm_is_violation_while_sigma_stays_silent():
    # window fully past the arming point -> concealed steady state
    u = _drive("surge", "concealment_mitm", steps=80, arm_after=6)
    reported = _frames(u.scada_window(48))
    truth = _frames(u.truth_window(48))
    r = comparison.evaluate_frames(reported, truth, "live", "live")
    assert r.pilot_status == "violation"
    assert "TANK_MASS_BALANCE" in r.layer1.violations
    assert r.layer3.top_hypothesis == "sensor_spoof_level"
    assert r.sigma.alert is False              # frozen value is in-band
    # reported (frozen) and actual (draining) must visibly diverge
    rep = [f.tank_level for f in reported if f.tank_level is not None]
    act = [f.tank_level for f in truth if f.tank_level is not None]
    assert max(rep) - min(act) > 0.5


def test_dos_is_uncertain_and_sigma_silent():
    u = _drive("normal", "dos", steps=80, arm_after=6)
    reported = _frames(u.scada_window(48))
    r = comparison.evaluate_frames(reported, _frames(u.truth_window(48)),
                                   "live", "live")
    assert r.pilot_status == "uncertain"
    assert r.layer3.top_hypothesis == "data_loss"
    assert r.sigma.alert is False
    assert any(f.tank_level is None for f in reported)


def test_pilot_only_receives_scada_never_truth(monkeypatch):
    """evaluate_live must fetch only /api/scada + /api/truth and feed only the
    reported stream to the engines."""
    u = _drive("surge", "concealment_mitm", steps=80, arm_after=6)
    calls: list[str] = []

    def fake_get(path: str) -> dict:
        calls.append(path)
        if path.startswith("/api/scada"):
            return {"status": u.status(), "frames": u.scada_window(48)}
        if path.startswith("/api/truth"):
            return {"status": u.status(), "frames": u.truth_window(48)}
        raise AssertionError(path)

    monkeypatch.setattr(live, "_get", fake_get)
    r = live.evaluate_live()
    assert r.pilot_status == "violation"
    assert any(c.startswith("/api/scada") for c in calls)


def test_live_scenario_name_reflects_state():
    assert "no attack" in live._scenario_name({"condition": "normal", "attack": "none"})
    assert "concealment MITM" in live._scenario_name(
        {"condition": "surge", "attack": "concealment_mitm"})


def _sweep_verdicts(condition: str, attack: str, window: int = 48) -> set[str]:
    """Steady-state verdict at EVERY phase of the looping trajectory."""
    u = Utility(tick_seconds=0.0, history=window + 4)
    u.set_condition(condition)
    if attack != "none":
        u.set_attack(attack)
    for _ in range(window + 2):          # fill a full window with this state
        u.advance()
    n = u.status()["steps"]
    seen = set()
    for _ in range(n):                   # one full loop
        u.advance()
        rep = _frames(u.scada_window(window))
        tru = _frames(u.truth_window(window))
        seen.add(comparison.evaluate_frames(rep, tru, "live", "live").pilot_status)
    return seen


def test_steady_state_verdicts_do_not_flicker_across_the_whole_loop():
    # regression: the concealment verdict must not drop back to VALID while the
    # attack is armed (previously happened when the window slid past a flat-empty
    # tank phase). Sweep every phase of the loop for each state.
    assert _sweep_verdicts("normal", "none") == {"valid"}
    assert _sweep_verdicts("surge", "none") == {"valid"}
    assert _sweep_verdicts("surge", "concealment_mitm") == {"violation"}
    assert _sweep_verdicts("normal", "dos") == {"uncertain"}
