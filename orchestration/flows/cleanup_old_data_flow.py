from datetime import datetime, timezone

from prefect import flow, task


@task(name="cleanup_timescaledb_retention")
def cleanup_timescaledb_retention() -> None:
    """
    Placeholder da limpeza do TimescaleDB.

    Futuramente este task irá:
    - validar políticas de retenção;
    - checar hypertables;
    - registrar status da limpeza.
    """
    print("[cleanup] TimescaleDB retention checked")


@task(name="cleanup_minio_old_raw_files")
def cleanup_minio_old_raw_files() -> None:
    """
    Placeholder da limpeza do data lake.

    Futuramente este task irá:
    - listar objetos antigos no MinIO;
    - aplicar retenção por prefixo;
    - preservar modelos versionados.
    """
    print("[cleanup] MinIO old raw files checked")


@task(name="cleanup_orchestration_logs")
def cleanup_orchestration_logs() -> None:
    """
    Placeholder da limpeza de logs/metadados de orquestração.
    """
    print(f"[cleanup] orchestration metadata checked at {datetime.now(timezone.utc).isoformat()}")


@flow(name="cleanup-old-data-flow")
def cleanup_old_data_flow() -> None:
    cleanup_timescaledb_retention()
    cleanup_minio_old_raw_files()
    cleanup_orchestration_logs()


if __name__ == "__main__":
    cleanup_old_data_flow()