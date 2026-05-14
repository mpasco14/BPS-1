from datetime import datetime, timezone

from prefect import flow, task


@task(name="fetch_onchain_events")
def fetch_onchain_events() -> dict:
    """
    Placeholder da atualização on-chain.

    Futuramente este task irá:
    - consultar Glassnode/CryptoQuant/Whale Alert;
    - calcular whale inflow/outflow;
    - publicar eventos no tópico onchain-events;
    - salvar dados brutos no MinIO.
    """
    return {
        "source": "placeholder",
        "event_type": "onchain_update",
        "metrics": [
            "exchange_inflow_btc",
            "exchange_outflow_btc",
            "whale_netflow",
            "miner_outflow",
        ],
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@task(name="publish_onchain_event")
def publish_onchain_event(payload: dict) -> None:
    """
    Placeholder para publicação no Redpanda.

    Futuramente publicará no tópico:
    - onchain-events
    """
    print(f"[onchain] payload={payload}")


@flow(name="update-onchain-flow")
def update_onchain_flow() -> None:
    payload = fetch_onchain_events()
    publish_onchain_event(payload)


if __name__ == "__main__":
    update_onchain_flow()