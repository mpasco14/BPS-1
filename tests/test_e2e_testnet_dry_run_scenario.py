from e2e.e2e_testnet_dry_run import run_e2e_testnet_dry_run_scenario


def test_e2e_testnet_dry_run_scenario_passes():
    report = run_e2e_testnet_dry_run_scenario(session_name="unit_testnet")

    assert report.passed is True
    assert report.scenario_kind == "testnet_dry_run"
    assert report.runtime_context["environment"] == "testnet"
    assert report.components["signal_pipeline"]["execution_contract"]["dry_run"] is True