from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()

__test__ = False


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def live_order_flags_detected() -> bool:
    return any(
        [
            env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
            env_bool("RISK_ALLOW_LIVE_TRADING", False),
            env_bool("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", False),
            env_bool("LIVE_ORDER_ADAPTER_ALLOW_LIVE_SUBMISSION", False),
        ]
    )


def export_json(
    payload: BaseModel | dict[str, Any],
    *,
    output_dir: str | Path,
    name: str,
) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    output_path = path / f"{name}.json"

    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path