from release_private.operator_daily_checklist import OperatorDailyChecklistInputs, build_operator_daily_checklist
from release_private.private_release_report import build_private_v1_release_report
from release_private.release_lock import ReleaseLockInputs, evaluate_release_lock
from release_private.release_models import PrivateReleaseConfig
from release_private.weekly_audit import WeeklyAuditInputs, build_weekly_audit_routine
from release_private.config_freeze import build_final_config_freeze_report
from release_private.evidence_pack import build_artifact_evidence_pack
from release_private.runbooks_review import review_final_runbooks


def test_private_release_report_ready_for_tag(tmp_path):
    config_file = tmp_path / ".env.example"
    config_file.write_text("API_SECRET=\n", encoding="utf-8")

    doc = tmp_path / "RUNBOOK.md"
    doc.write_text("# Runbook\n", encoding="utf-8")

    artifact = tmp_path / "pytest_full.log"
    artifact.write_text("11 passed\n", encoding="utf-8")

    release_config = PrivateReleaseConfig(
        required_docs=[str(doc)],
        required_artifacts=[str(artifact)],
        require_artifacts=False,
    )

    release_lock = evaluate_release_lock(
        inputs=ReleaseLockInputs(
            branch="main",
            git_clean=True,
            upstream_synced=True,
            tests_passed=True,
            tag_exists=False,
        ),
        config=release_config,
    )
    freeze = build_final_config_freeze_report(config_files=[str(config_file)])
    runbooks = review_final_runbooks(config=release_config)
    evidence = build_artifact_evidence_pack(config=release_config)
    daily = build_operator_daily_checklist(
        inputs=OperatorDailyChecklistInputs(
            operator_name="Paulo",
            read_runbook=True,
            git_clean_confirmed=True,
            env_checked=True,
            no_live_flags_confirmed=True,
            emergency_shutdown_ready=True,
            artifacts_dir_available=True,
            session_goal_defined=True,
        )
    )
    weekly = build_weekly_audit_routine(
        inputs=WeeklyAuditInputs(
            operator_name="Paulo",
            reviewed_trades=True,
            reviewed_rejections=True,
            reviewed_risk_limits=True,
            reviewed_artifacts=True,
            reviewed_config_changes=True,
            reviewed_security=True,
            reviewed_model_drift=True,
            reviewed_runbooks=True,
        )
    )

    report = build_private_v1_release_report(
        release_lock=release_lock,
        config_freeze=freeze,
        runbooks_review=runbooks,
        evidence_pack=evidence,
        operator_daily_checklist=daily,
        weekly_audit=weekly,
        config=release_config,
    )

    assert report.passed is True
    assert report.decision == "READY_FOR_TAG"