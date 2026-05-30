from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from testnet_campaign.multi_session_review import (
    build_multi_session_review,
    export_multi_session_review_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review multiple real testnet campaign reports.")

    parser.add_argument("--reports", nargs="+", required=True)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--name", default="multi_session_testnet_review")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    report = build_multi_session_review(report_paths=args.reports)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_multi_session_review_report(report, name=args.name)
        print(f"Multi-session review exported to: {path}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())