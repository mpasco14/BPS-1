from __future__ import annotations

from pathlib import Path

from release_private.release_models import ComponentReport, PrivateReleaseConfig, export_release_json, load_private_release_config, sha256_file


def build_artifact_evidence_pack(
    *,
    config: PrivateReleaseConfig | None = None,
) -> ComponentReport:
    resolved = config or load_private_release_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []
    artifacts: list[dict] = []

    for item in resolved.required_artifacts:
        path = Path(item)

        if not path.exists():
            if resolved.require_artifacts:
                blockers.append(f"required_artifact_missing:{item}")
            else:
                warnings.append(f"artifact_missing:{item}")
            continue

        artifacts.append(
            {
                "path": item,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )

    if not artifacts:
        warnings.append("no_release_artifacts_indexed")

    recommendations.append("Artifacts são evidências operacionais; não commitar se contiverem dados sensíveis.")
    recommendations.append("Guardar logs de pytest, read-only, testnet lifecycle, campaign e micro-live gate.")
    recommendations.append("Antes de tag final, rodar validação V1 e gerar artifacts atualizados.")

    passed = not blockers

    return ComponentReport(
        source="private_release_artifact_evidence_pack",
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        metadata={
            "artifacts": artifacts,
            "required_artifacts": resolved.required_artifacts,
            "strict_required": resolved.require_artifacts,
        },
    )


def export_artifact_evidence_pack_report(
    report: ComponentReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "private_release_artifact_evidence_pack",
) -> Path:
    return export_release_json(report, output_dir=output_dir, name=name)