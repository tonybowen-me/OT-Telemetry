from app import ingestion


def test_list_scenarios_present():
    scen = ingestion.list_scenarios()
    assert set(scen) == {"normal", "operational_demand_surge", "concealment_mitm", "dos_incomplete"}


def test_frames_normalise_and_relevance_filter():
    sc = ingestion.load_scenario("normal")
    assert len(sc.reported) == len(sc.ground_truth) > 0
    f = sc.reported[0]
    # canonical typed fields
    assert isinstance(f.iteration, int)
    assert isinstance(f.tank_level, float)
    # relevance filter: only known fields survive
    assert set(f.model_dump().keys()) >= {"tank_level", "tank_inflow", "pump1_status"}


def test_missing_values_become_none():
    sc = ingestion.load_scenario("dos_incomplete")
    assert any(f.tank_level is None for f in sc.reported)
    assert any(f.missing == 1 for f in sc.reported)


def test_unknown_scenario_raises():
    try:
        ingestion.load_scenario("does_not_exist")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass
