from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


RetryErrorKind = Literal["network", "rate_limit", "server_error", "timeout", "client_error", "unknown"]
RetryDecisionStatus = Literal["RETRY", "DO_NOT_RETRY", "GIVE_UP"]


class RetryPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/infra")

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 10.0
    multiplier: float = 2.0
    jitter_pct: float = 0.0

    retryable_status_codes: list[int] = Field(default_factory=lambda: [408, 409, 425, 429, 500, 502, 503, 504])
    non_retryable_status_codes: list[int] = Field(default_factory=lambda: [400, 401, 403, 404, 422])


class RetryContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    operation_name: str
    attempt: int = 1

    error_kind: RetryErrorKind = "unknown"
    status_code: int | None = None
    exception_name: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class RetryDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "retry_policy"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    operation_name: str
    status: RetryDecisionStatus
    should_retry: bool

    attempt: int
    next_attempt: int | None = None
    delay_seconds: float | None = None

    reason: str
    context: dict[str, Any]
    config: dict[str, Any]


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


def load_retry_policy_config() -> RetryPolicyConfig:
    return RetryPolicyConfig(
        output_dir=Path(os.getenv("RETRY_POLICY_OUTPUT_DIR", "artifacts/infra")),
        max_attempts=env_int("RETRY_MAX_ATTEMPTS", 3),
        base_delay_seconds=env_float("RETRY_BASE_DELAY_SECONDS", 0.5),
        max_delay_seconds=env_float("RETRY_MAX_DELAY_SECONDS", 10),
        multiplier=env_float("RETRY_MULTIPLIER", 2),
        jitter_pct=env_float("RETRY_JITTER_PCT", 0),
    )


def classify_status_code(status_code: int | None, config: RetryPolicyConfig) -> tuple[bool, str, RetryErrorKind]:
    if status_code is None:
        return True, "status_code_missing_treat_as_retryable_unknown", "unknown"

    if status_code in config.retryable_status_codes:
        if status_code == 429:
            return True, "rate_limit_retryable", "rate_limit"

        if status_code >= 500:
            return True, "server_error_retryable", "server_error"

        return True, "status_code_retryable", "unknown"

    if status_code in config.non_retryable_status_codes:
        return False, "status_code_non_retryable", "client_error"

    if status_code >= 500:
        return True, "server_error_retryable", "server_error"

    if 400 <= status_code < 500:
        return False, "client_error_non_retryable", "client_error"

    return True, "status_code_unknown_retryable", "unknown"


def calculate_backoff_delay(
    *,
    attempt: int,
    config: RetryPolicyConfig,
) -> float:
    attempt_index = max(0, attempt - 1)
    delay = config.base_delay_seconds * (config.multiplier ** attempt_index)
    delay = min(delay, config.max_delay_seconds)

    if config.jitter_pct > 0:
        delay = delay * (1 + min(config.jitter_pct, 1.0))

    return round(delay, 6)


def evaluate_retry_decision(
    *,
    context: RetryContext | dict[str, Any],
    config: RetryPolicyConfig | None = None,
) -> RetryDecision:
    resolved_config = config or load_retry_policy_config()
    resolved_context = context if isinstance(context, RetryContext) else RetryContext.model_validate(context)

    if resolved_context.attempt >= resolved_config.max_attempts:
        return RetryDecision(
            operation_name=resolved_context.operation_name,
            status="GIVE_UP",
            should_retry=False,
            attempt=resolved_context.attempt,
            reason="max_attempts_reached",
            context=resolved_context.model_dump(mode="json"),
            config=resolved_config.model_dump(mode="json"),
        )

    retryable_by_kind = resolved_context.error_kind in {"network", "rate_limit", "server_error", "timeout", "unknown"}
    retryable_by_status, status_reason, inferred_kind = classify_status_code(resolved_context.status_code, resolved_config)

    retryable = retryable_by_kind and retryable_by_status

    if not retryable:
        return RetryDecision(
            operation_name=resolved_context.operation_name,
            status="DO_NOT_RETRY",
            should_retry=False,
            attempt=resolved_context.attempt,
            reason=status_reason,
            context=resolved_context.model_copy(update={"error_kind": inferred_kind}).model_dump(mode="json"),
            config=resolved_config.model_dump(mode="json"),
        )

    delay = calculate_backoff_delay(
        attempt=resolved_context.attempt,
        config=resolved_config,
    )

    return RetryDecision(
        operation_name=resolved_context.operation_name,
        status="RETRY",
        should_retry=True,
        attempt=resolved_context.attempt,
        next_attempt=resolved_context.attempt + 1,
        delay_seconds=delay,
        reason=status_reason,
        context=resolved_context.model_copy(update={"error_kind": inferred_kind}).model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_retry_decision(
    decision: RetryDecision,
    *,
    output_dir: str | Path | None = None,
    name: str = "retry_decision_latest",
) -> Path:
    config = load_retry_policy_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(decision.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path