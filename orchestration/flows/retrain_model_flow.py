from datetime import datetime, timezone

from prefect import flow, task


@task(name="load_training_dataset")
def load_training_dataset() -> dict:
    """
    Placeholder para carregar dataset de treinamento.

    Futuramente este task irá:
    - ler features históricas do TimescaleDB e/ou MinIO;
    - montar dataset de treino;
    - validar qualidade dos dados.
    """
    return {
        "dataset": "placeholder",
        "features": [
            "technical_score",
            "onchain_score",
            "sentiment_score",
            "microstructure_score",
            "prob_yes",
            "edge_yes",
        ],
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@task(name="train_model")
def train_model(dataset: dict) -> dict:
    """
    Placeholder do treinamento.

    Futuramente este task irá:
    - treinar LightGBM/XGBoost;
    - calibrar probabilidades;
    - calcular Brier score/log loss;
    - versionar modelo.
    """
    print(f"[model] training dataset={dataset}")
    return {
        "model_version": "v0.1.0-placeholder",
        "status": "trained_placeholder",
    }


@task(name="store_model_artifacts")
def store_model_artifacts(model_metadata: dict) -> None:
    """
    Placeholder para salvar artefatos.

    Futuramente salvará em:
    - models/version={version}/ no MinIO.
    """
    print(f"[model] metadata={model_metadata}")


@flow(name="retrain-model-flow")
def retrain_model_flow() -> None:
    dataset = load_training_dataset()
    model_metadata = train_model(dataset)
    store_model_artifacts(model_metadata)


if __name__ == "__main__":
    retrain_model_flow()