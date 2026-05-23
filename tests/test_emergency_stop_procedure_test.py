from ops.emergency_stop_procedure_test import (
    EmergencyStopProcedureInputs,
    build_emergency_stop_procedure_report,
)


def test_emergency_stop_procedure_passes():
    report = build_emergency_stop_procedure_report(
        inputs=EmergencyStopProcedureInputs(
            kill_switch_activated=True,
            cancel_all_orders_called=True,
            open_orders_after_cancel=0,
            new_orders_blocked=True,
            safe_mode_active=True,
            notification_sent=True,
        )
    )

    assert report.passed is True


def test_emergency_stop_procedure_blocks_open_orders():
    report = build_emergency_stop_procedure_report(
        inputs=EmergencyStopProcedureInputs(
            kill_switch_activated=True,
            cancel_all_orders_called=True,
            open_orders_after_cancel=2,
            new_orders_blocked=True,
            safe_mode_active=True,
            notification_sent=True,
        )
    )

    assert report.passed is False
    assert "NO_OPEN_ORDERS_AFTER_CANCEL_FAILED" in report.blockers