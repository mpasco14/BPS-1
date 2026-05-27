from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config_management.config_registry import build_default_config_registry, export_config_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run config registry demo.")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--path", default="artifacts/config/config_registry_demo.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = build_default_config_registry()

    print(json.dumps(registry.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_config_registry(registry, path=args.path)
        print(f"Config registry exported: {path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())