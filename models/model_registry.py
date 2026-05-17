"""
Model registry.

Responsabilidades:
- Versionar modelos, calibradores, métricas e schemas.
- Salvar metadados em JSON.
- Resolver o modelo mais recente por nome.
- Manter rastreabilidade para backtest, paper trading e produção.

Este módulo NÃO treina modelos.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


load_dotenv()


class ModelRegistryRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    model_name: str
    model_version: str

    model_type: str
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"

    feature_columns: list[str]

    model_path: str | None = None
    calibrator_path: str | None = None

    metrics: dict[str, Any] = Field(default_factory=dict)
    training_period: dict[str, Any] = Field(default_factory=dict)

    dataset_hash: str | None = None
    artifact_hash: str | None = None

    approved_for_paper: bool = False
    approved_for_live: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model_name", "model_version", "model_type")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("campo obrigatório vazio")

        return value

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


def utc_version(prefix: str | None = None) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if prefix:
        return f"{prefix}_{stamp}"

    return stamp


def sha256_json(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: str | Path) -> str:
    file_path = Path(path)
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def registry_dir(path: str | Path | None = None) -> Path:
    resolved = Path(path or os.getenv("MODEL_REGISTRY_DIR", "artifacts/model_registry"))
    resolved.mkdir(parents=True, exist_ok=True)

    return resolved


def record_path(
    record: ModelRegistryRecord,
    *,
    base_dir: str | Path | None = None,
) -> Path:
    safe_name = record.model_name.replace("/", "_").replace("\\", "_")
    safe_version = record.model_version.replace("/", "_").replace("\\", "_")

    return registry_dir(base_dir) / safe_name / f"{safe_version}.json"


def latest_pointer_path(
    model_name: str,
    *,
    base_dir: str | Path | None = None,
) -> Path:
    safe_name = model_name.replace("/", "_").replace("\\", "_")

    return registry_dir(base_dir) / safe_name / "latest.json"


def save_registry_record(
    record: ModelRegistryRecord,
    *,
    base_dir: str | Path | None = None,
) -> Path:
    path = record_path(record, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    update_latest_pointer(record, base_dir=base_dir)

    return path


def load_registry_record(path: str | Path) -> ModelRegistryRecord:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    return ModelRegistryRecord.model_validate(payload)


def update_latest_pointer(
    record: ModelRegistryRecord,
    *,
    base_dir: str | Path | None = None,
) -> Path:
    pointer = latest_pointer_path(record.model_name, base_dir=base_dir)
    pointer.parent.mkdir(parents=True, exist_ok=True)

    pointer.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return pointer


def load_latest_record(
    model_name: str,
    *,
    base_dir: str | Path | None = None,
) -> ModelRegistryRecord:
    return load_registry_record(
        latest_pointer_path(model_name, base_dir=base_dir)
    )


def register_model(
    *,
    model_name: str,
    model_version: str,
    model_type: str,
    feature_columns: list[str],
    model_path: str | None = None,
    calibrator_path: str | None = None,
    metrics: dict[str, Any] | None = None,
    dataset_payload: Any | None = None,
    metadata: dict[str, Any] | None = None,
    base_dir: str | Path | None = None,
) -> ModelRegistryRecord:
    artifact_hash = None

    if model_path and Path(model_path).exists():
        artifact_hash = sha256_file(model_path)

    dataset_hash = None

    if dataset_payload is not None:
        dataset_hash = sha256_json(dataset_payload)

    record = ModelRegistryRecord(
        model_name=model_name,
        model_version=model_version,
        model_type=model_type,
        feature_columns=feature_columns,
        model_path=model_path,
        calibrator_path=calibrator_path,
        metrics=metrics or {},
        dataset_hash=dataset_hash,
        artifact_hash=artifact_hash,
        metadata=metadata or {},
    )

    save_registry_record(record, base_dir=base_dir)

    return record