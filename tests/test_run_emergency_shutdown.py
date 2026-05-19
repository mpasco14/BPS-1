import json
from argparse import Namespace

from scripts.run_emergency_shutdown import load_orders_json, resolve_dry_run


def test_load_orders_json(tmp_path):
    path = tmp_path / "orders.json"
    path.write_text(
        json.dumps(
            [
                {
                    "symbol": "BTCUSDT",
                    "client_order_id": "client-1",
                    "order_id": 123,
                    "side": "BUY",
                    "price": 60000,
                    "quantity": 0.01,
                }
            ]
        ),
        encoding="utf-8",
    )

    orders = load_orders_json(path)

    assert len(orders) == 1
    assert orders[0]["symbol"] == "BTCUSDT"


def test_resolve_dry_run_execute_false():
    args = Namespace(
        execute=True,
        dry_run=False,
    )

    assert resolve_dry_run(args) is False


def test_resolve_dry_run_explicit_true():
    args = Namespace(
        execute=False,
        dry_run=True,
    )

    assert resolve_dry_run(args) is True