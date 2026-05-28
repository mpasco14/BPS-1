from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from data_persistence.retention_policy import RetentionPolicyConfig, evaluate_retention_policy, export_retention_policy_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run data retention policy.")

    parser.add_argument("--root", default="artifacts")
    parser.add_argument("--max-age-days", type=int, default=None)
    parser.add_argument("--delete", action="store_true", help="Actually delete files. Default is dry-run.")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/storage")
    parser.add_argument("--name", default="retention_policy_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    config = RetentionPolicyConfig(
        dry_run=not args.delete,
        max_age_days=args.max_age_days if args.max_age_days is not None else 30,
    )

    report = evaluate_retention_policy(root=args.root, config=config)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_retention_policy_report(report, output_dir=args.output_dir, name=args.name)
        print(f"Retention policy report exported: {path}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())