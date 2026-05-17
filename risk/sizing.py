"""
Fractional Kelly sizing.

Responsabilidades:
- Calcular tamanho de posição com Kelly fracionado.
- Aplicar caps por bankroll e liquidez.
- Nunca operar acima do Kelly calculado.

Este módulo NÃO aprova sinal sozinho.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


class SizingPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    bankroll_usd: float
    edge: float
    odds: float

    raw_kelly_fraction: float
    reduction_factor: float
    fractional_kelly_fraction: float

    kelly_position_usd: float
    bankroll_cap_usd: float
    liquidity_cap_usd: float

    final_position_usd: float
    is_tradeable: bool

    blockers: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def calculate_expected_value(
    *,
    prob_win: float,
    profit_usd: float,
    loss_usd: float,
    fees_usd: float = 0.0,
) -> float:
    return prob_win * profit_usd - (1 - prob_win) * loss_usd - fees_usd


def calculate_edge_ratio(
    *,
    expected_value_usd: float,
    loss_usd: float,
) -> float:
    if loss_usd <= 0:
        return 0.0

    return expected_value_usd / loss_usd


def calculate_kelly_fraction(
    *,
    edge: float,
    odds: float,
) -> float:
    if odds <= 0:
        return 0.0

    return max(0.0, edge / odds)


def calculate_fractional_kelly_position(
    *,
    bankroll_usd: float,
    edge: float,
    odds: float,
    market_liquidity_usd: float,
    reduction_factor: float | None = None,
    max_bankroll_pct: float | None = None,
    max_liquidity_pct: float | None = None,
    min_position_usd: float | None = None,
) -> SizingPlan:
    reduction = reduction_factor if reduction_factor is not None else env_float("KELLY_REDUCTION_FACTOR", 0.10)
    max_reduction = env_float("KELLY_MAX_REDUCTION_FACTOR", 0.25)
    reduction = min(reduction, max_reduction)

    bankroll_cap_pct = max_bankroll_pct if max_bankroll_pct is not None else env_float("SIZING_MAX_BANKROLL_PCT", 0.005)
    liquidity_pct = max_liquidity_pct if max_liquidity_pct is not None else env_float("SIZING_MAX_MARKET_LIQUIDITY_PCT", 0.05)
    min_position = min_position_usd if min_position_usd is not None else env_float("SIZING_MIN_POSITION_USD", 1.0)

    raw_kelly = calculate_kelly_fraction(edge=edge, odds=odds)
    fractional = raw_kelly * reduction

    kelly_position = bankroll_usd * fractional
    bankroll_cap = bankroll_usd * bankroll_cap_pct
    liquidity_cap = market_liquidity_usd * liquidity_pct

    final_position = min(bankroll_cap, kelly_position, liquidity_cap)

    blockers: list[str] = []
    reasons: list[str] = [
        f"raw_kelly_fraction:{raw_kelly:.6f}",
        f"fractional_kelly_fraction:{fractional:.6f}",
        f"bankroll_cap_usd:{bankroll_cap:.6f}",
        f"liquidity_cap_usd:{liquidity_cap:.6f}",
    ]

    if edge <= 0:
        blockers.append("non_positive_edge")

    if odds <= 0:
        blockers.append("invalid_odds")

    if final_position < min_position:
        blockers.append("position_below_minimum")

    return SizingPlan(
        bankroll_usd=bankroll_usd,
        edge=edge,
        odds=odds,
        raw_kelly_fraction=raw_kelly,
        reduction_factor=reduction,
        fractional_kelly_fraction=fractional,
        kelly_position_usd=kelly_position,
        bankroll_cap_usd=bankroll_cap,
        liquidity_cap_usd=liquidity_cap,
        final_position_usd=max(0.0, final_position),
        is_tradeable=not blockers,
        blockers=blockers,
        reasons=reasons,
    )


def sizing_plan_to_dict(plan: SizingPlan) -> dict[str, Any]:
    return plan.model_dump(mode="json")