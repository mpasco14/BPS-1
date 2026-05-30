from __future__ import annotations
from binance_testnet_adapter.sanitization import sanitize_artifact_payload
import os
from pathlib import Path
from typing import Any
from binance_testnet_adapter.sanitization import sanitize_artifact_payload
from binance_testnet_adapter.account_snapshot import fetch_binance_testnet_account_snapshot
from binance_testnet_adapter.position_reconciliation import reconcile_binance_testnet_position
from testnet_order_lifecycle.cancel_order import cancel_real_testnet_order
from testnet_order_lifecycle.fill_rejection_capture import capture_testnet_fill_rejection
from testnet_order_lifecycle.lifecycle_models import (
    TestnetOrderLifecycleConfig,
    TestnetOrderLifecycleEvent,
    TestnetOrderLifecycleReport,
    export_lifecycle_json,
    load_testnet_order_lifecycle_config,
    validate_lifecycle_config,
)
from testnet_order_lifecycle.open_order_query import query_real_testnet_open_order
from testnet_order_lifecycle.small_limit_order_submit import submit_real_testnet_small_limit_order
from testnet_order_lifecycle.test_order_validation import validate_real_testnet_test_order
from testnet_readiness.testnet_portfolio_reconciliation import build_flat_position


def extract_client_order_id_from_submit(submit_report: dict[str, Any]) -> str | None:
    request = submit_report.get("request") or {}
    if isinstance(request, dict):
        return request.get("new_client_order_id")

    return None


def extract_order_id_from_response(report: dict[str, Any]) -> int | None:
    response = report.get("response") or {}
    data = response.get("data") if isinstance(response, dict) else None

    if isinstance(data, dict):
        value = data.get("orderId")
        return int(value) if value is not None else None

    return None


def build_real_testnet_lifecycle_report(
    *,
    config: TestnetOrderLifecycleConfig | None = None,
) -> TestnetOrderLifecycleReport:
    resolved = config or load_testnet_order_lifecycle_config()
    blockers = validate_lifecycle_config(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []
    events: list[TestnetOrderLifecycleEvent] = []

    if blockers:
        return TestnetOrderLifecycleReport(
            status="BLOCKED",
            passed=False,
            simulated=resolved.simulate,
            symbol=resolved.symbol,
            blockers=blockers,
            warnings=warnings,
            recommendations=[
                "Corrigir configuração antes de qualquer validação de ordem testnet.",
                "Manter live flags desligadas.",
            ],
            events=[],
            config=sanitize_artifact_payload(resolved.model_dump(mode="json")),
        )

    test_order = validate_real_testnet_test_order(config=resolved)
    events.append(
        TestnetOrderLifecycleEvent(
            event_type="TEST_ORDER_VALIDATED" if test_order.passed else "TEST_ORDER_FAILED",
            symbol=resolved.symbol,
            passed=test_order.passed,
            blockers=test_order.blockers,
            warnings=test_order.warnings,
            payload=test_order.model_dump(mode="json"),
        )
    )

    if resolved.require_test_order_pass and not test_order.passed:
        blockers.append("test_order_validation_not_passed")

    submit = None
    query = None
    cancel = None
    fill_capture = None
    position_recon = None

    client_order_id = None
    order_id = None

    if not blockers:
        submit = submit_real_testnet_small_limit_order(
            config=resolved,
            force_dry_run=resolved.simulate,
        )
        submit_dump = submit.model_dump(mode="json")
        client_order_id = extract_client_order_id_from_submit(submit_dump)
        order_id = extract_order_id_from_response(submit_dump)

        if submit.status == "DRY_RUN":
            event_type = "ORDER_SUBMIT_DRY_RUN"
        elif submit.submitted:
            event_type = "ORDER_SUBMITTED"
        elif submit.status == "BLOCKED":
            event_type = "ORDER_SUBMIT_BLOCKED"
        else:
            event_type = "ORDER_SUBMIT_FAILED"

        events.append(
            TestnetOrderLifecycleEvent(
                event_type=event_type,
                symbol=resolved.symbol,
                client_order_id=client_order_id,
                order_id=order_id,
                passed=submit.passed,
                blockers=submit.blockers,
                warnings=submit.warnings,
                payload=submit_dump,
            )
        )

        if not submit.passed:
            blockers.append("small_limit_order_submit_not_passed")
            blockers.extend([f"submit:{item}" for item in submit.blockers])

    if not blockers and client_order_id:
        query = query_real_testnet_open_order(
            client_order_id=client_order_id,
            order_id=order_id,
            config=resolved,
        )
        query_dump = query.model_dump(mode="json")

        events.append(
            TestnetOrderLifecycleEvent(
                event_type="OPEN_ORDER_FOUND" if query.passed else "OPEN_ORDER_NOT_FOUND",
                symbol=resolved.symbol,
                client_order_id=client_order_id,
                order_id=order_id,
                passed=query.passed,
                blockers=query.blockers,
                warnings=query.warnings,
                payload=query_dump,
            )
        )

        if not query.passed and not resolved.simulate:
            warnings.append("open_order_query_not_passed_may_be_filled_or_not_open")

    if not blockers and client_order_id:
        cancel = cancel_real_testnet_order(
            client_order_id=client_order_id,
            order_id=order_id,
            config=resolved,
        )
        cancel_dump = cancel.model_dump(mode="json")

        events.append(
            TestnetOrderLifecycleEvent(
                event_type="ORDER_CANCELED" if cancel.canceled else "ORDER_CANCEL_BLOCKED" if cancel.status == "BLOCKED" else "ORDER_CANCEL_FAILED",
                symbol=resolved.symbol,
                client_order_id=client_order_id,
                order_id=order_id,
                passed=cancel.passed,
                blockers=cancel.blockers,
                warnings=cancel.warnings,
                payload=cancel_dump,
            )
        )

        if resolved.require_cancel_attempt and cancel.status == "BLOCKED" and not resolved.simulate:
            blockers.append("cancel_order_blocked_in_real_testnet_lifecycle")

    fill_capture = capture_testnet_fill_rejection(
        submit=submit,
        query=query,
        cancel=cancel,
    )
    events.append(
        TestnetOrderLifecycleEvent(
            event_type="REJECTION_DETECTED" if fill_capture.rejection_detected else "FILL_DETECTED" if fill_capture.fill_detected else "FINAL_REPORT",
            symbol=resolved.symbol,
            client_order_id=client_order_id,
            order_id=order_id,
            passed=fill_capture.passed,
            blockers=fill_capture.blockers,
            warnings=fill_capture.warnings,
            payload=fill_capture.model_dump(mode="json"),
        )
    )

    if not fill_capture.passed:
        blockers.append("fill_rejection_capture_not_passed")
        blockers.extend([f"fill_capture:{item}" for item in fill_capture.blockers])

    account = fetch_binance_testnet_account_snapshot(symbol=resolved.symbol)
    position_recon = reconcile_binance_testnet_position(
        local_position=build_flat_position(resolved.symbol),
        account_snapshot=account,
        symbol=resolved.symbol,
    )

    events.append(
        TestnetOrderLifecycleEvent(
            event_type="POSITION_RECONCILED",
            symbol=resolved.symbol,
            passed=position_recon.passed,
            blockers=position_recon.blockers,
            warnings=position_recon.warnings,
            payload=position_recon.model_dump(mode="json"),
        )
    )

    if resolved.require_final_flat and not position_recon.passed:
        blockers.append("final_position_reconciliation_not_passed")
        blockers.extend([f"position:{item}" for item in position_recon.blockers])

    warnings.extend(test_order.warnings)
    if submit:
        warnings.extend([f"submit:{item}" for item in submit.warnings])
    if query:
        warnings.extend([f"query:{item}" for item in query.warnings])
    if cancel:
        warnings.extend([f"cancel:{item}" for item in cancel.warnings])
    warnings.extend([f"fill_capture:{item}" for item in fill_capture.warnings])
    warnings.extend([f"position:{item}" for item in position_recon.warnings])

    recommendations.append("No modo simulado, usar este relatório apenas como validação estrutural.")
    recommendations.append("No modo real testnet, só avançar se ordem for consultada/cancelada ou preenchida com reconciliação final PASS.")
    recommendations.append("Não avançar para micro-live sem múltiplas sessões testnet reais aprovadas.")

    passed = not blockers

    return TestnetOrderLifecycleReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        simulated=resolved.simulate,
        symbol=resolved.symbol,
        client_order_id=client_order_id,
        order_id=order_id,
        test_order_passed=test_order.passed,
        submit_passed=submit.passed if submit else False,
        submitted=submit.submitted if submit else False,
        open_order_query_passed=query.passed if query else False,
        cancel_attempted=cancel is not None,
        cancel_passed=cancel.passed if cancel else False,
        fill_detected=fill_capture.fill_detected if fill_capture else False,
        rejection_detected=fill_capture.rejection_detected if fill_capture else False,
        final_flat=position_recon.passed if position_recon else False,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        events=[item.model_dump(mode="json") for item in events],
        test_order=test_order.model_dump(mode="json"),
        submit=submit.model_dump(mode="json") if submit else None,
        open_order_query=query.model_dump(mode="json") if query else None,
        cancel=cancel.model_dump(mode="json") if cancel else None,
        fill_capture=fill_capture.model_dump(mode="json") if fill_capture else None,
        position_reconciliation=position_recon.model_dump(mode="json") if position_recon else None,
        config=sanitize_artifact_payload(resolved.model_dump(mode="json")),
    )


def export_real_testnet_lifecycle_report(
    report: TestnetOrderLifecycleReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "real_testnet_order_lifecycle_report",
) -> Path:
    return export_lifecycle_json(
        report,
        output_dir=output_dir or os.getenv("TESTNET_ORDER_LIFECYCLE_REPORT_OUTPUT_DIR", "artifacts/testnet_order_lifecycle"),
        name=name,
    )