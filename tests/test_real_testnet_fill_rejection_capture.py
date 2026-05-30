from binance_testnet_adapter.order_cancel import BinanceTestnetCancelOrderReport
from binance_testnet_adapter.order_submit import BinanceTestnetOrderSubmitReport
from testnet_order_lifecycle.fill_rejection_capture import capture_testnet_fill_rejection


def test_fill_rejection_capture_passes_with_cancel():
    submit = BinanceTestnetOrderSubmitReport(
        status="SUBMITTED",
        passed=True,
        submitted=True,
        dry_run=False,
        simulated=True,
        request={"quantity": 0.001},
        response={"data": {"status": "NEW"}},
        config={},
    )
    cancel = BinanceTestnetCancelOrderReport(
        status="CANCELED",
        passed=True,
        canceled=True,
        simulated=True,
        request={},
        response={"data": {"status": "CANCELED"}},
        config={},
    )

    report = capture_testnet_fill_rejection(
        submit=submit,
        cancel=cancel,
    )

    assert report.passed is True
    assert report.cancel_detected is True