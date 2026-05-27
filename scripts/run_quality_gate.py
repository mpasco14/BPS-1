from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from quality.ci_quality_gate import (
    build_quality_check_from_command,
    default_quality_commands,
    evaluate_quality_gate,
    export_quality_gate_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local quality gate.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output", default="artifacts/quality/quality_gate_report.json")
    parser.add_argument("--skip-pytest", action="store_true")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    commands = default_quality_commands()

    if args.skip_pytest:
        commands = [item for item in commands if item["check_id"] != "pytest_full"]

    checks = []

    for index, spec in enumerate(commands, start=1):
        print(f"[{index}/{len(commands)}] Running {spec['check_id']}...", flush=True)

        check = build_quality_check_from_command(
            check_id=spec["check_id"],
            name=spec["name"],
            command=spec["command"],
            severity=spec["severity"],
            blocking=spec["blocking"],
            timeout_seconds=spec["timeout_seconds"],
        )

        print(f"[{index}/{len(commands)}] {check.check_id}: {check.status}", flush=True)
        checks.append(check)

    report = evaluate_quality_gate(checks=checks)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_quality_gate_report(report, path=args.output)
        print(f"Quality gate report exported: {path}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())