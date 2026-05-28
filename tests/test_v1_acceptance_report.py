from v1_acceptance.operator_checklist import build_v1_operator_checklist, evaluate_operator_checklist
from v1_acceptance.v1_acceptance_report import build_v1_acceptance_report, component_from_report
from v1_acceptance.v1_contracts import build_default_v1_contract_bundle, evaluate_v1_contracts


def test_v1_acceptance_report_accepts_demo():
    contracts = evaluate_v1_contracts(
        contracts=build_default_v1_contract_bundle()
    )

    checklist = evaluate_operator_checklist(
        checklist=build_v1_operator_checklist(
            operator="Paulo",
            mark_demo_passed=True,
        )
    )

    components = [
        component_from_report(name="pytest", passed=True, status="PASS"),
        component_from_report(name="e2e", passed=True, status="PASS"),
        component_from_report(name="scenario_testing", passed=True, status="PASS"),
        component_from_report(name="testnet_acceptance", passed=True, status="ACCEPTED"),
        component_from_report(name="security", passed=True, status="PASS"),
        component_from_report(name="docs", passed=True, status="PASS"),
    ]

    report = build_v1_acceptance_report(
        contracts_report=contracts,
        operator_checklist_report=checklist,
        components=components,
    )

    assert report.accepted is True
    assert report.paper_ready is True
    assert report.testnet_ready is True
    assert report.live_ready is False


def test_v1_acceptance_report_blocks_missing_component():
    contracts = evaluate_v1_contracts(
        contracts=build_default_v1_contract_bundle()
    )

    checklist = evaluate_operator_checklist(
        checklist=build_v1_operator_checklist(
            operator="Paulo",
            mark_demo_passed=True,
        )
    )

    report = build_v1_acceptance_report(
        contracts_report=contracts,
        operator_checklist_report=checklist,
        components=[
            component_from_report(name="pytest", passed=True, status="PASS"),
        ],
    )

    assert report.accepted is False
    assert "e2e_component_missing" in report.blockers