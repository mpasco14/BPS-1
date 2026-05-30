from release_private.operator_daily_checklist import OperatorDailyChecklistInputs, build_operator_daily_checklist
from release_private.weekly_audit import WeeklyAuditInputs, build_weekly_audit_routine


def test_operator_daily_checklist_passes_all_confirmed():
    report = build_operator_daily_checklist(
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

    assert report.passed is True


def test_weekly_audit_passes_all_confirmed():
    report = build_weekly_audit_routine(
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

    assert report.passed is True