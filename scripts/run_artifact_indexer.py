from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from data_persistence.artifact_indexer import build_artifact_index_report, export_artifact_index_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run artifact indexer.")

    parser.add_argument("--root", default="artifacts")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--path", default="artifacts/storage/artifact_index.json")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    report = build_artifact_index_report(root=args.root)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_artifact_index_report(report, path=args.path)
        print(f"Artifact index exported: {path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())