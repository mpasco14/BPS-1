"""
Model calibration evaluation runner.

Uso demo:

    python scripts/evaluate_model_calibration.py --demo --name calibration_demo

Uso com arquivo JSON/JSONL:

    python scripts/evaluate_model_calibration.py ^
        --predictions artifacts/model_predictions/predictions.jsonl ^
        --name calibration_001

Formato aceito por linha/registro:

    {
      "target": 1,
      "prob_tp": 0.73
    }

Também aceita:
- y_true
- outcome_final
- outcome
- y_prob
- probability
- prob
- calibrated_prob_tp
- prediction.prob_tp
- prediction.calibrated_prob_tp
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


from models.evaluate_calibration import (
    CalibrationEvaluationReport,
    evaluate_probability_calibration,
    export_calibration_report,
    plot_calibration_curve,
)
from scripts.run_paper_trading_session import load_json_or_jsonl


def build_demo_predictions() -> list[dict[str, Any]]:
    return [
        {"target": 0, "prob_tp": 0.05},
        {"target": 0, "prob_tp": 0.15},
        {"target": 0, "prob_tp": 0.25},
        {"target": 1, "prob_tp": 0.65},
        {"target": 1, "prob_tp": 0.75},
        {"target": 1, "prob_tp": 0.85},
        {"target": 1, "prob_tp": 0.95},
        {"target": 0, "prob_tp": 0.35},
        {"target": 1, "prob_tp": 0.70},
        {"target": 0, "prob_tp": 0.20},
    ]


def load_prediction_rows(path: str | Path) -> list[dict[str, Any]]:
    payload = load_json_or_jsonl(path)

    if isinstance(payload, list):
        return [dict(item) for item in payload]

    if isinstance(payload, dict) and isinstance(payload.get("predictions"), list):
        return [dict(item) for item in payload["predictions"]]

    raise ValueError("predictions precisa ser lista JSON/JSONL ou dict com chave 'predictions'.")


def parse_target(row: dict[str, Any]) -> int:
    for key in ["target", "y_true", "label"]:
        value = row.get(key)

        if value is None:
            continue

        parsed = int(float(value))

        if parsed not in {0, 1}:
            raise ValueError(f"target inválido: {value}")

        return parsed

    for key in ["outcome_final", "outcome", "label_name"]:
        value = row.get(key)

        if value is None:
            continue

        text = str(value).strip().lower()

        if text in {"1", "win", "take_profit", "tp", "true", "yes"}:
            return 1

        if text in {"0", "loss", "stop_loss", "sl", "false", "no"}:
            return 0

    raise ValueError(f"target não encontrado no registro: {row}")


def parse_probability(row: dict[str, Any]) -> float:
    for key in [
        "y_prob",
        "prob_tp",
        "calibrated_prob_tp",
        "probability",
        "prob",
        "prediction_probability",
    ]:
        value = row.get(key)

        if value is None:
            continue

        parsed = float(value)

        return max(0.0, min(1.0, parsed))

    prediction = row.get("prediction")

    if isinstance(prediction, dict):
        for key in ["calibrated_prob_tp", "prob_tp", "probability", "prob"]:
            value = prediction.get(key)

            if value is None:
                continue

            parsed = float(value)

            return max(0.0, min(1.0, parsed))

    raise ValueError(f"probabilidade não encontrada no registro: {row}")


def extract_calibration_arrays(rows: list[dict[str, Any]]) -> tuple[list[int], list[float]]:
    y_true: list[int] = []
    y_prob: list[float] = []

    for row in rows:
        y_true.append(parse_target(row))
        y_prob.append(parse_probability(row))

    return y_true, y_prob


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate probability calibration for model predictions."
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Usa predições simuladas.",
    )
    parser.add_argument(
        "--predictions",
        type=str,
        default=None,
        help="Arquivo JSON/JSONL com predições.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="calibration_report",
        help="Nome do relatório.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="artifacts/model_evaluation",
        help="Diretório de saída.",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=10,
        help="Número de buckets de calibração.",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Gera imagem PNG da calibration curve.",
    )

    return parser.parse_args()


def load_rows_from_args(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.demo:
        return build_demo_predictions()

    if not args.predictions:
        raise SystemExit("Use --demo ou informe --predictions.")

    return load_prediction_rows(args.predictions)


def run_calibration_evaluation_from_rows(
    rows: list[dict[str, Any]],
    *,
    bins: int,
) -> CalibrationEvaluationReport:
    y_true, y_prob = extract_calibration_arrays(rows)

    return evaluate_probability_calibration(
        y_true=y_true,
        y_prob=y_prob,
        n_bins=bins,
    )


def main() -> int:
    args = parse_args()

    rows = load_rows_from_args(args)
    report = run_calibration_evaluation_from_rows(
        rows,
        bins=args.bins,
    )

    report_path = export_calibration_report(
        report,
        output_dir=args.output_dir,
        name=args.name,
    )

    print("Calibration evaluation completed")
    print(f"Report: {report_path}")
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.plot:
        plot_path = Path(args.output_dir) / f"{args.name}_curve.png"

        try:
            plot_calibration_curve(
                report,
                output_path=plot_path,
            )

            print(f"Plot: {plot_path}")
        except RuntimeError as exc:
            print(f"Plot skipped: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())