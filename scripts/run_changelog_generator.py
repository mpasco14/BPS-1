from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from release_management.changelog_generator import CommitRecord, build_changelog_report, export_changelog_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate changelog.")

    parser.add_argument("--version", default="0.17.0")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/release")

    return parser.parse_args()


def demo_commits() -> list[CommitRecord]:
    return [
        CommitRecord(sha="abc1234", message="feat: add release management flow"),
        CommitRecord(sha="def5678", message="docs: add release runbook"),
        CommitRecord(sha="aaa9999", message="fix: improve quality gate behavior"),
    ]


def main() -> int:
    args = parse_args()

    report = build_changelog_report(
        version=args.version,
        commits=demo_commits() if args.demo else None,
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        json_path, md_path = export_changelog_report(report, output_dir=args.output_dir)
        print(f"Changelog JSON exported: {json_path}", flush=True)
        print(f"Changelog Markdown exported: {md_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())