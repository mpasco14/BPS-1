from datetime import datetime, timezone

from prefect import flow, task


@task(name="fetch_btc_candles")
def fetch_btc_candles() -> dict:
    """
    Placeholder da ingestão de candles.

    Futuramente este task irá:
    - ler candles BTC da Binance/Coinbase/Bybit;
    - publicar eventos no tópico btc-candles;
    - persistir dados no TimescaleDB;
    - salvar raw parquet no MinIO.
    """
    return {
        "source": "placeholder",
        "symbol": "BTCUSDT",
        "timeframes": ["5m", "15m", "1h", "1D"],
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@task(name="publish_candles_event")
def publish_candles_event(payload: dict) -> None:
    """
    Placeholder para publicação no Redpanda.

    Futuramente publicará no tópico:
    - btc-candles
    """
    print(f"[candles] payload={payload}")


@flow(name="ingest-candles-flow")
def ingest_candles_flow() -> None:
    payload = fetch_btc_candles()
    publish_candles_event(payload)


if __name__ == "__main__":
    ingest_candles_flow()