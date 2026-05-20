from risk.risk_state import (
    OpenPositionSnapshot,
    RiskStateConfig,
    build_risk_state_snapshot,
    export_risk_state_snapshot,
    load_risk_state_snapshot,
)


def test_build_risk_state_ok():
    snapshot = build_risk_state_snapshot(
        open_positions=[
            OpenPositionSnapshot(
                symbol="BTCUSDT",
                side="LONG",
                quantity=0.01,
                entry_price=60000,
                notional_usd=600,
                margin_usd=20,
                leverage=30,
                timeframe="5m",
            )
        ],
        config=RiskStateConfig(max_total_exposure_usd=600),
    )

    assert snapshot.status == "OK"
    assert snapshot.total_open_positions == 1
    assert snapshot.total_exposure_usd == 600


def test_risk_state_blocks_daily_loss():
    snapshot = build_risk_state_snapshot(
        daily_realized_pnl_usd=-10,
        config=RiskStateConfig(max_daily_loss_usd=5),
    )

    assert snapshot.status == "BLOCKED"
    assert "daily_loss_limit_reached" in snapshot.blockers


def test_export_and_load_risk_state(tmp_path):
    snapshot = build_risk_state_snapshot()

    path = export_risk_state_snapshot(snapshot, path=tmp_path / "risk.json")
    loaded = load_risk_state_snapshot(path)

    assert path.exists()
    assert loaded is not None
    assert loaded.source == "risk_state"