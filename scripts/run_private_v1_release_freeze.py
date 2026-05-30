from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from release_private.config_freeze import build_final_config_freeze_report, export_final_config_freeze_report
from release_private.evidence_pack import build_artifact_evidence_pack, export_artifact_evidence_pack_report
from release_private.operator_daily_checklist import build_operator_daily_checklist, export_operator_daily_checklist_report
from release_private.private_release_report import build_private_v1_release_report, export_private_v1_release_report
from release_private.release_lock import evaluate_release_lock, export_release_lock_report, inspect_release_lock_inputs
from release_private.release_models import load_private_release_config
from release_private.runbooks_review import export_final_runbooks_review_report, review_final_runbooks
from release_private.weekly_audit import build_weekly_audit_routine, export_weekly_audit_routine_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run private V1 release freeze.")

    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/private_release")
    parser.add_argument("--name", default="v1_0_0_private_release")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    config = load_private_release_config()

    lock_inputs = inspect_release_lock_inputs(
        release_version=config.release_version,
        tests_passed=args.tests_passed,
    )
    release_lock = evaluate_release_lock(inputs=lock_inputs, config=config)
    config_freeze = build_final_config_freeze_report()
    runbooks = review_final_runbooks(config=config)
    evidence = build_artifact_evidence_pack(config=config)
    daily = build_operator_daily_checklist(config=config)
    weekly = build_weekly_audit_routine(config=config)

    report = build_private_v1_release_report(
        release_lock=release_lock,
        config_freeze=config_freeze,
        runbooks_review=runbooks,
        evidence_pack=evidence,
        operator_daily_checklist=daily,
        weekly_audit=weekly,
        config=config,
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        output_dir.mkdir(parents=True, exist_ok=True)

        export_release_lock_report(release_lock, output_dir=output_dir, name=f"{args.name}_release_lock")
        export_final_config_freeze_report(config_freeze, output_dir=output_dir, name=f"{args.name}_config_freeze")
        export_final_runbooks_review_report(runbooks, output_dir=output_dir, name=f"{args.name}_runbooks_review")
        export_artifact_evidence_pack_report(evidence, output_dir=output_dir, name=f"{args.name}_evidence_pack")
        export_operator_daily_checklist_report(daily, output_dir=output_dir, name=f"{args.name}_daily_checklist")
        export_weekly_audit_routine_report(weekly, output_dir=output_dir, name=f"{args.name}_weekly_audit")
        export_private_v1_release_report(report, output_dir=output_dir, name=f"{args.name}_final_report")

        print(f"Private V1 release artifacts exported to: {output_dir}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())