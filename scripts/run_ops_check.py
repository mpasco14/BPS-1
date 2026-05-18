"""
Run compliance and security checks.

Uso:

    python scripts/run_ops_check.py

Exportando relatórios:

    python scripts/run_ops_check.py --export

Nome customizado:

    python scripts/run_ops_check.py --export --name pre_live_check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.compliance_check import export_compliance_report, run_compliance_checks
from ops.security_check import export_security_report, run_security_checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run BTC Binance Futures ops compliance/security checks."
    )

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", type=str, default="artifacts/ops")
    parser.add_argument("--name", type=str, default="ops_latest")

    return parser.parse_args()


def build_ops_payload() -> dict:
    compliance = run_compliance_checks()
    security = run_security_checks()

    passed = compliance.passed and security.passed

    return {
        "source": "ops_check",
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "compliance": compliance.model_dump(mode="json"),
        "security": security.model_dump(mode="json"),
    }


def export_ops_payload(
    payload: dict,
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

    payload = build_ops_payload()

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.export:
        output_path = export_ops_payload(
            payload,
            output_dir=args.output_dir,
            name=args.name,
        )

        export_compliance_report(
            run_compliance_checks(),
            output_dir=args.output_dir,
            name=f"{args.name}_compliance",
        )

        export_security_report(
            run_security_checks(),
            output_dir=args.output_dir,
            name=f"{args.name}_security",
        )

        print(f"Ops report exported: {output_path}")

    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())