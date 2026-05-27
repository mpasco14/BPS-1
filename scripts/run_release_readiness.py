from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from quality.ci_quality_gate import QualityGateReport
from quality.release_readiness import (
    evaluate_release_readiness,
    export_release_readiness_report,
    inputs_from_quality_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate release readiness.")

    parser.add_argument("--quality-report", default="artifacts/quality/quality_gate_report.json")
    parser.add_argument("--version", default="unversioned")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/quality")
    parser.add_argument("--name", default="release_readiness_latest")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    quality_report_path = Path(args.quality_report)

    if not quality_report_path.exists():
        print(f"Quality report not found: {quality_report_path}", flush=True)
        return 1

    quality_gate = QualityGateReport.model_validate_json(
        quality_report_path.read_text(encoding="utf-8")
    )

    inputs = inputs_from_quality_gate(
        quality_gate=quality_gate,
        version=args.version,
    )

    report = evaluate_release_readiness(inputs=inputs)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_release_readiness_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Release readiness report exported: {path}", flush=True)

    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())