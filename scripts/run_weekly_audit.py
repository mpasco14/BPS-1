"""
Run weekly audit and retraining protocol.

Exemplos:

    python scripts/run_weekly_audit.py
    python scripts/run_weekly_audit.py --export --name weekly_audit_demo
    python scripts/run_weekly_audit.py --candidate-json artifacts/model_candidate/candidate_metrics.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.audit_report import build_weekly_audit_report, export_weekly_audit_report
from ops.retraining_protocol import (
    ModelValidationMetrics,
    evaluate_retraining_candidate,
    export_retraining_report,
)


def load_metrics_json(path: str | Path | None) -> ModelValidationMetrics | None:
    if path is None:
        return None

    input_path = Path(path)

    if not input_path.exists():
        raise FileNotFoundError(f"metrics file not found: {input_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))

    return ModelValidationMetrics.model_validate(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run BTC Binance Futures weekly audit and retraining protocol."
    )

    parser.add_argument("--candidate-json", type=str, default=None)
    parser.add_argument("--current-json", type=str, default=None)

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", type=str, default="artifacts/ops")
    parser.add_argument("--name", type=str, default="weekly_audit_latest")

    return parser.parse_args()


def build_weekly_payload(
    *,
    candidate: ModelValidationMetrics | None = None,
    current: ModelValidationMetrics | None = None,
) -> dict[str, Any]:
    audit = build_weekly_audit_report()
    retraining = evaluate_retraining_candidate(
        candidate=candidate,
        current=current,
    )

    return {
        "source": "weekly_audit_runner",
        "passed": audit.passed and retraining.passed,
        "status": "PASS" if audit.passed and retraining.passed else "FAIL",
        "audit": audit.model_dump(mode="json"),
        "retraining": retraining.model_dump(mode="json"),
    }


def export_weekly_payload(
    payload: dict[str, Any],
    *,
    output_dir: str | Path,
    name: str,
) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def main() -> int:
    args = parse_args()

    candidate = load_metrics_json(args.candidate_json)
    current = load_metrics_json(args.current_json)

    payload = build_weekly_payload(
        candidate=candidate,
        current=current,
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.export:
        output_path = export_weekly_payload(
            payload,
            output_dir=args.output_dir,
            name=args.name,
        )

        export_weekly_audit_report(
            build_weekly_audit_report(),
            output_dir=args.output_dir,
            name=f"{args.name}_audit",
        )

        export_retraining_report(
            evaluate_retraining_candidate(
                candidate=candidate,
                current=current,
            ),
            output_dir=args.output_dir,
            name=f"{args.name}_retraining",
        )

        print(f"Weekly audit exported: {output_path}")

    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())