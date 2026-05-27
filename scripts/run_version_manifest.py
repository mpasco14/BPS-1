from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from release_management.version_pinning import (
    build_release_version_manifest,
    build_version_pin,
    export_version_manifest,
    export_version_manifest_validation_report,
    validate_version_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate version manifest.")

    parser.add_argument("--version", default="0.17.0")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--manifest-path", default="artifacts/release/version_manifest.json")
    parser.add_argument("--output-dir", default="artifacts/release")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    pins = [
        build_version_pin(name="core_code", kind="code", version=args.version, path="pyproject.toml", required=True),
        build_version_pin(name="model_lgbm", kind="model", version="demo-model-v1", required=True),
        build_version_pin(name="runtime_config", kind="config", version="demo-config-v1", required=True),
    ]

    manifest = build_release_version_manifest(
        release_version=args.version,
        pins=pins,
        metadata={"environment": "controlled_release"},
    )

    validation = validate_version_manifest(manifest)

    print(json.dumps(validation.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        manifest_path = export_version_manifest(manifest, path=args.manifest_path)
        report_path = export_version_manifest_validation_report(
            validation,
            output_dir=args.output_dir,
            name="version_manifest_validation_demo",
        )
        print(f"Version manifest exported: {manifest_path}", flush=True)
        print(f"Version manifest validation exported: {report_path}", flush=True)

    return 0 if validation.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())