from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


DependencyStatus = Literal["PASS", "WARN", "FAIL", "SKIP"]
DependencyKind = Literal["redis", "kafka", "binance_rest", "binance_ws", "filesystem", "service", "other"]


class DependencyHealthConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/infra")
    max_latency_ms: float = 2000.0
    require_critical: bool = True


class DependencyProbeSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    kind: DependencyKind = "other"
    critical: bool = True

    host: str | None = None
    port: int | None = None
    path: str | None = None

    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class DependencyProbeResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    kind: DependencyKind = "other"
    critical: bool = True

    status: DependencyStatus
    message: str

    latency_ms: float | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    metadata: dict[str, Any] = Field(default_factory=dict)


class DependencyHealthReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "dependency_health"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    dependencies_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    skip_count: int
    critical_fail_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


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


def load_dependency_health_config() -> DependencyHealthConfig:
    return DependencyHealthConfig(
        output_dir=Path(os.getenv("DEPENDENCY_HEALTH_OUTPUT_DIR", "artifacts/infra")),
        max_latency_ms=env_float("DEPENDENCY_HEALTH_MAX_LATENCY_MS", 2000),
        require_critical=env_bool("DEPENDENCY_HEALTH_REQUIRE_CRITICAL", True),
    )


def tcp_probe(spec: DependencyProbeSpec, *, timeout_seconds: float = 2.0) -> DependencyProbeResult:
    if not spec.host or spec.port is None:
        return DependencyProbeResult(
            name=spec.name,
            kind=spec.kind,
            critical=spec.critical,
            status="SKIP",
            message="Host ou porta ausente para probe TCP.",
            metadata=spec.metadata,
        )

    start = time.perf_counter()

    try:
        with socket.create_connection((spec.host, spec.port), timeout=timeout_seconds):
            latency_ms = (time.perf_counter() - start) * 1000

        return DependencyProbeResult(
            name=spec.name,
            kind=spec.kind,
            critical=spec.critical,
            status="PASS",
            message="Conexão TCP bem-sucedida.",
            latency_ms=round(latency_ms, 4),
            metadata=spec.metadata,
        )

    except OSError as exc:
        latency_ms = (time.perf_counter() - start) * 1000

        return DependencyProbeResult(
            name=spec.name,
            kind=spec.kind,
            critical=spec.critical,
            status="FAIL",
            message=f"Falha na conexão TCP: {exc}",
            latency_ms=round(latency_ms, 4),
            metadata=spec.metadata,
        )


def filesystem_probe(spec: DependencyProbeSpec) -> DependencyProbeResult:
    if not spec.path:
        return DependencyProbeResult(
            name=spec.name,
            kind=spec.kind,
            critical=spec.critical,
            status="SKIP",
            message="Path ausente para probe de filesystem.",
            metadata=spec.metadata,
        )

    path = Path(spec.path)

    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".healthcheck"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)

        return DependencyProbeResult(
            name=spec.name,
            kind=spec.kind,
            critical=spec.critical,
            status="PASS",
            message="Filesystem gravável.",
            metadata={"path": str(path), **spec.metadata},
        )

    except OSError as exc:
        return DependencyProbeResult(
            name=spec.name,
            kind=spec.kind,
            critical=spec.critical,
            status="FAIL",
            message=f"Filesystem não gravável: {exc}",
            metadata={"path": str(path), **spec.metadata},
        )


def run_dependency_probe(spec: DependencyProbeSpec) -> DependencyProbeResult:
    if not spec.enabled:
        return DependencyProbeResult(
            name=spec.name,
            kind=spec.kind,
            critical=spec.critical,
            status="SKIP",
            message="Dependency probe desabilitado.",
            metadata=spec.metadata,
        )

    if spec.kind == "filesystem":
        return filesystem_probe(spec)

    if spec.host and spec.port is not None:
        return tcp_probe(spec)

    return DependencyProbeResult(
        name=spec.name,
        kind=spec.kind,
        critical=spec.critical,
        status="WARN",
        message="Dependency sem probe ativo configurado. Usando status WARN.",
        metadata=spec.metadata,
    )


def default_dependency_specs() -> list[DependencyProbeSpec]:
    return [
        DependencyProbeSpec(
            name="artifacts_filesystem",
            kind="filesystem",
            critical=True,
            path=os.getenv("INFRA_OUTPUT_DIR", "artifacts/infra"),
        ),
        DependencyProbeSpec(
            name="redis",
            kind="redis",
            critical=False,
            host=os.getenv("REDIS_HOST"),
            port=int(os.getenv("REDIS_PORT", "6379")) if os.getenv("REDIS_HOST") else None,
            enabled=bool(os.getenv("REDIS_HOST")),
        ),
        DependencyProbeSpec(
            name="kafka",
            kind="kafka",
            critical=False,
            host=os.getenv("KAFKA_HOST"),
            port=int(os.getenv("KAFKA_PORT", "9092")) if os.getenv("KAFKA_HOST") else None,
            enabled=bool(os.getenv("KAFKA_HOST")),
        ),
    ]


def build_dependency_health_report(
    *,
    probe_results: list[DependencyProbeResult | dict[str, Any]] | None = None,
    probe_specs: list[DependencyProbeSpec | dict[str, Any]] | None = None,
    config: DependencyHealthConfig | None = None,
) -> DependencyHealthReport:
    resolved_config = config or load_dependency_health_config()

    if probe_results is not None:
        results = [
            item if isinstance(item, DependencyProbeResult) else DependencyProbeResult.model_validate(item)
            for item in probe_results
        ]
    else:
        specs = [
            item if isinstance(item, DependencyProbeSpec) else DependencyProbeSpec.model_validate(item)
            for item in (probe_specs if probe_specs is not None else default_dependency_specs())
        ]
        results = [run_dependency_probe(spec) for spec in specs]

    blockers: list[str] = []
    warnings: list[str] = []

    for item in results:
        if item.status == "FAIL" and item.critical and resolved_config.require_critical:
            blockers.append(item.name)
        elif item.status in {"FAIL", "WARN"}:
            warnings.append(item.name)

        if item.latency_ms is not None and item.latency_ms > resolved_config.max_latency_ms:
            warnings.append(f"{item.name}:latency_above_limit")

    pass_count = sum(1 for item in results if item.status == "PASS")
    warn_count = sum(1 for item in results if item.status == "WARN")
    fail_count = sum(1 for item in results if item.status == "FAIL")
    skip_count = sum(1 for item in results if item.status == "SKIP")
    critical_fail_count = sum(1 for item in results if item.status == "FAIL" and item.critical)

    passed = len(blockers) == 0

    return DependencyHealthReport(
        passed=passed,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        dependencies_count=len(results),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        skip_count=skip_count,
        critical_fail_count=critical_fail_count,
        blockers=blockers,
        warnings=warnings,
        dependencies=[item.model_dump(mode="json") for item in results],
        config=resolved_config.model_dump(mode="json"),
    )


def export_dependency_health_report(
    report: DependencyHealthReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "dependency_health_latest",
) -> Path:
    config = load_dependency_health_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path