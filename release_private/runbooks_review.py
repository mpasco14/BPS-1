from __future__ import annotations

from pathlib import Path

from release_private.release_models import ComponentReport, PrivateReleaseConfig, export_release_json, load_private_release_config, sha256_file


def review_final_runbooks(
    *,
    config: PrivateReleaseConfig | None = None,
) -> ComponentReport:
    resolved = config or load_private_release_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []
    docs: list[dict] = []

    for item in resolved.required_docs:
        path = Path(item)

        if not path.exists():
            if resolved.require_docs:
                blockers.append(f"required_runbook_missing:{item}")
            else:
                warnings.append(f"runbook_missing:{item}")
            continue

        if path.stat().st_size == 0:
            blockers.append(f"runbook_empty:{item}")
            continue

        docs.append(
            {
                "path": item,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )

    recommendations.append("Operador deve ler runbooks antes de testnet real ou micro-live.")
    recommendations.append("Runbook de emergência precisa estar acessível offline.")

    passed = not blockers

    return ComponentReport(
        source="private_release_final_runbooks_review",
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        metadata={"reviewed_docs": docs},
    )


def export_final_runbooks_review_report(
    report: ComponentReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "private_release_runbooks_review",
) -> Path:
    return export_release_json(report, output_dir=output_dir, name=name)