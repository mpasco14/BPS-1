from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


ConfigValueType = Literal["str", "int", "float", "bool", "json"]


class ConfigRegistryConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/config")
    registry_file: Path = Path("artifacts/config/config_registry.json")
    environment: str = "development"
    default_profile: str = "conservative"


class ConfigRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    value: Any
    value_type: ConfigValueType = "str"

    scope: str = "global"
    environment: str = "development"

    description: str | None = None
    sensitive: bool = False
    locked: bool = False

    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class CentralConfigRegistry(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "central_config_registry"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    environment: str = "development"
    profile: str = "conservative"

    records: list[dict[str, Any]] = Field(default_factory=list)


def load_config_registry_config() -> ConfigRegistryConfig:
    return ConfigRegistryConfig(
        output_dir=Path(os.getenv("CONFIG_MANAGEMENT_OUTPUT_DIR", "artifacts/config")),
        registry_file=Path(os.getenv("CONFIG_REGISTRY_FILE", "artifacts/config/config_registry.json")),
        environment=os.getenv("CONFIG_ENVIRONMENT", "development"),
        default_profile=os.getenv("CONFIG_DEFAULT_PROFILE", "conservative"),
    )


def normalize_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_")


def infer_value_type(value: Any) -> ConfigValueType:
    if isinstance(value, bool):
        return "bool"

    if isinstance(value, int) and not isinstance(value, bool):
        return "int"

    if isinstance(value, float):
        return "float"

    if isinstance(value, dict | list):
        return "json"

    return "str"


def cast_config_value(value: Any, value_type: ConfigValueType) -> Any:
    if value_type == "bool":
        if isinstance(value, bool):
            return value

        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    if value_type == "int":
        return int(value)

    if value_type == "float":
        return float(value)

    if value_type == "json":
        if isinstance(value, str):
            return json.loads(value)

        return value

    return str(value)


def create_config_record(
    *,
    key: str,
    value: Any,
    value_type: ConfigValueType | None = None,
    scope: str = "global",
    environment: str | None = None,
    description: str | None = None,
    sensitive: bool = False,
    locked: bool = False,
    metadata: dict[str, Any] | None = None,
) -> ConfigRecord:
    config = load_config_registry_config()
    resolved_type = value_type or infer_value_type(value)

    return ConfigRecord(
        key=normalize_key(key),
        value=cast_config_value(value, resolved_type),
        value_type=resolved_type,
        scope=scope,
        environment=environment or config.environment,
        description=description,
        sensitive=sensitive,
        locked=locked,
        metadata=metadata or {},
    )


def build_central_config_registry(
    *,
    records: list[ConfigRecord | dict[str, Any]] | None = None,
    environment: str | None = None,
    profile: str | None = None,
) -> CentralConfigRegistry:
    config = load_config_registry_config()

    parsed = [
        item if isinstance(item, ConfigRecord) else ConfigRecord.model_validate(item)
        for item in (records or [])
    ]

    return CentralConfigRegistry(
        environment=environment or config.environment,
        profile=profile or config.default_profile,
        records=[item.model_dump(mode="json") for item in parsed],
    )


def registry_records(registry: CentralConfigRegistry | dict[str, Any]) -> list[ConfigRecord]:
    parsed = registry if isinstance(registry, CentralConfigRegistry) else CentralConfigRegistry.model_validate(registry)

    return [ConfigRecord.model_validate(item) for item in parsed.records]


def get_config_record(
    registry: CentralConfigRegistry | dict[str, Any],
    key: str,
    *,
    environment: str | None = None,
    scope: str | None = None,
) -> ConfigRecord | None:
    target = normalize_key(key)
    records = registry_records(registry)

    for record in reversed(records):
        if record.key != target:
            continue

        if environment is not None and record.environment != environment:
            continue

        if scope is not None and record.scope != scope:
            continue

        return record

    return None


def get_config_value(
    registry: CentralConfigRegistry | dict[str, Any],
    key: str,
    *,
    default: Any = None,
    environment: str | None = None,
    scope: str | None = None,
) -> Any:
    record = get_config_record(registry, key, environment=environment, scope=scope)

    if record is None:
        return default

    return cast_config_value(record.value, record.value_type)


def upsert_config_record(
    registry: CentralConfigRegistry,
    record: ConfigRecord,
) -> CentralConfigRegistry:
    records = registry_records(registry)
    replaced = False

    for index, existing in enumerate(records):
        if existing.key == record.key and existing.scope == record.scope and existing.environment == record.environment:
            if existing.locked:
                raise ValueError(f"Config key is locked: {existing.key}")

            records[index] = record
            replaced = True
            break

    if not replaced:
        records.append(record)

    return build_central_config_registry(
        records=records,
        environment=registry.environment,
        profile=registry.profile,
    )


def build_default_config_registry() -> CentralConfigRegistry:
    config = load_config_registry_config()

    records = [
        create_config_record(
            key="execution_mode",
            value=os.getenv("BINANCE_EXECUTION_MODE", "paper"),
            scope="execution",
            environment=config.environment,
            description="Current execution mode.",
        ),
        create_config_record(
            key="allow_live_trading",
            value=os.getenv("BINANCE_ALLOW_LIVE_TRADING", "false"),
            value_type="bool",
            scope="execution",
            environment=config.environment,
            description="Whether live trading is allowed.",
            locked=True,
        ),
        create_config_record(
            key="live_order_adapter_dry_run",
            value=os.getenv("LIVE_ORDER_ADAPTER_DRY_RUN", "true"),
            value_type="bool",
            scope="execution",
            environment=config.environment,
            description="Live order adapter dry-run mode.",
            locked=True,
        ),
        create_config_record(
            key="strategy_profile",
            value=config.default_profile,
            scope="strategy",
            environment=config.environment,
            description="Default strategy profile.",
        ),
        create_config_record(
            key="max_leverage",
            value=os.getenv("STRATEGY_PROFILE_MAX_LEVERAGE", "30"),
            value_type="int",
            scope="risk",
            environment=config.environment,
            description="Maximum leverage allowed by config.",
            locked=True,
        ),
    ]

    return build_central_config_registry(
        records=records,
        environment=config.environment,
        profile=config.default_profile,
    )


def export_config_registry(
    registry: CentralConfigRegistry,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_config_registry_config()
    output_path = Path(path or config.registry_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(registry.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def load_config_registry(path: str | Path | None = None) -> CentralConfigRegistry | None:
    config = load_config_registry_config()
    input_path = Path(path or config.registry_file)

    if not input_path.exists():
        return None

    return CentralConfigRegistry.model_validate_json(input_path.read_text(encoding="utf-8"))