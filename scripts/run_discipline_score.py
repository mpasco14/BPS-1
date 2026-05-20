from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.discipline_score import (
    DisciplinePolicyEvent,
    build_discipline_score_report,
    export_discipline_score_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run discipline score demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/governance")
    parser.add_argument("--name", default="discipline_score_demo")

    return parser.parse_args()


def demo_events() -> list[DisciplinePolicyEvent]:
    return [
        DisciplinePolicyEvent(
            event_id="discipline_demo_1",
            pillar="risk",
            rule_code="risk_approved",
            passed=True,
            severity="HIGH",
            message="Risk manager approved.",
        ),
        DisciplinePolicyEvent(
            event_id="discipline_demo_2",
            pillar="execution",
            rule_code="execution_guard_approved",
            passed=True,
            severity="HIGH",
            message="Execution guard approved.",
        ),
        DisciplinePolicyEvent(
            event_id="discipline_demo_3",
            pillar="data_quality",
            rule_code="data_quality_passed",
            passed=True,
            severity="HIGH",
            message="Data quality passed.",
        ),
    ]


def main() -> int:
    args = parse_args()

    report = build_discipline_score_report(events=demo_events())

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_discipline_score_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Discipline score exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())