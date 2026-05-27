from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from release_management.release_candidate_checklist import (
    ReleaseCandidateInputs,
    evaluate_release_candidate_checklist,
    export_release_candidate_checklist_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate release candidate checklist.")

    parser.add_argument("--version", default="0.17.0")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/release")
    parser.add_argument("--name", default="release_candidate_checklist_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    report = evaluate_release_candidate_checklist(
        inputs=ReleaseCandidateInputs(
            version=args.version,
            quality_gate_passed=True,
            tests_passed=True,
            security_passed=True,
            infra_passed=True,
            docs_present=True,
            changelog_present=True,
            version_manifest_present=True,
            model_pinned=True,
            config_pinned=True,
            deployment_plan_present=True,
            git_clean=True,
        )
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_release_candidate_checklist_report(report, output_dir=args.output_dir, name=args.name)
        print(f"Release candidate checklist exported: {path}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())