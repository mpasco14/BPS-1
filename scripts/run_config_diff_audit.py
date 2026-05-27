from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config_management.config_diff_audit import (
    ConfigAuditRecord,
    append_config_audit_record,
    build_config_diff_report,
    export_config_diff_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run config diff audit demo.")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/config")
    parser.add_argument("--name", default="config_diff_demo")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    before = {
        "strategy": {
            "profile": "conservative",
            "min_confidence": 0.65,
        }
    }

    after = {
        "strategy": {
            "profile": "balanced",
            "min_confidence": 0.62,
        }
    }

    report = build_config_diff_report(before=before, after=after)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_config_diff_report(report, output_dir=args.output_dir, name=args.name)

        audit_path = append_config_audit_record(
            ConfigAuditRecord(
                actor="operator",
                reason="Demo config diff audit.",
                environment="development",
                diff=report.model_dump(mode="json"),
            )
        )

        print(f"Config diff exported: {path}", flush=True)
        print(f"Config audit record appended: {audit_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())