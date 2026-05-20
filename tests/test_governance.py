from ops.governance import (
    GovernanceConfig,
    GovernanceEvidence,
    evaluate_governance,
    export_governance_report,
)


def full_evidence():
    return GovernanceEvidence(
        model_available=True,
        calibration_available=True,
        ood_detection_available=True,
        feedback_dataset_available=True,
        decision_journal_available=True,
        order_lifecycle_available=True,
        audit_reports_available=True,
        model_registry_available=True,
        risk_manager_available=True,
        live_guard_available=True,
        capital_ramp_available=True,
        preflight_available=True,
        live_disabled_by_default=True,
        secrets_not_committed=True,
        testnet_separated=True,
        compliance_available=True,
        kill_switch_available=True,
        emergency_shutdown_available=True,
        health_checks_available=True,
        alerting_available=True,
    )


def test_governance_passes_with_full_evidence():
    report = evaluate_governance(
        evidence=full_evidence(),
        config=GovernanceConfig(),
    )

    assert report.passed is True
    assert report.status == "PASS"


def test_governance_fails_missing_intelligence():
    evidence = full_evidence()
    evidence.model_available = False

    report = evaluate_governance(
        evidence=evidence,
        config=GovernanceConfig(),
    )

    assert report.passed is False
    assert any(check["code"] == "INTELLIGENCE_MODEL_AVAILABLE" for check in report.checks)


def test_export_governance_report(tmp_path):
    report = evaluate_governance(
        evidence=full_evidence(),
        config=GovernanceConfig(),
    )

    path = export_governance_report(
        report,
        output_dir=tmp_path,
        name="unit_governance",
    )

    assert path.exists()