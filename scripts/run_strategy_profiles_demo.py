from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config_management.strategy_profiles import (
    build_default_strategy_profiles,
    export_strategy_profiles,
    validate_strategy_profile,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run strategy profiles demo.")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--path", default="artifacts/config/strategy_profiles_demo.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    profiles = build_default_strategy_profiles()
    reports = [validate_strategy_profile(profile=profile) for profile in profiles]

    print(json.dumps([item.model_dump(mode="json") for item in reports], ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_strategy_profiles(profiles, path=args.path)
        print(f"Strategy profiles exported: {path}", flush=True)

    return 0 if all(item.passed for item in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())