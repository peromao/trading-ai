"""Helpers to apply AI-suggested orders and persist portfolio side effects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type, datetime
from typing import Iterable, Optional

import math

from app.data.collector import get_latest_cash_before, get_portfolio
from app.data.inserter import insert_cash_snapshot, sync_positions_with_portfolio
from app.openai_integration import Order
from app.portfolio_manager import (
    CashSnapshot,
    Portfolio,
    apply_orders,
    compute_cash_after_orders,
)


@dataclass(frozen=True)
class PostTradeResult:
    """Represents the persisted outcome of applying a batch of orders."""

    as_of_date: date_type
    previous_cash: float
    new_cash: float
    orders_count: int
    position_sync: dict[str, int]


def _normalize_cash(value: Optional[object]) -> float:
    if value is None:
        return 0.0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(numeric) else numeric


def apply_orders_and_persist(
    orders: Iterable[Order],
    *,
    as_of_date: Optional[date_type] = None,
    portfolio_override: Optional[Portfolio] = None,
    prior_cash_row: Optional[dict] = None,
) -> PostTradeResult:
    """Apply executed orders, sync positions, and write the resulting cash snapshot.

    Args:
        orders: Executed orders to reflect in the portfolio.
        as_of_date: Optional override for the cash snapshot date (defaults to today UTC).
        portfolio_override: Optional pre-loaded portfolio to avoid re-fetching.
        prior_cash_row: Optional cached result from ``get_latest_cash_before``.
    """

    orders_list = [order for order in orders or []]

    portfolio = portfolio_override or get_portfolio()
    updated_portfolio = apply_orders(portfolio, orders_list)
    position_sync = sync_positions_with_portfolio(updated_portfolio)

    if as_of_date is None:
        as_of_date = datetime.utcnow().date()

    prior = prior_cash_row or get_latest_cash_before(as_of_date)
    prev_amount = prior.get("amount") if prior else None
    previous_cash = _normalize_cash(prev_amount)

    new_cash = compute_cash_after_orders(previous_cash, orders_list)

    snapshot = CashSnapshot(
        date=as_of_date,
        amount=new_cash,
        total_portfolio_amount=None,
    )
    insert_cash_snapshot(snapshot)

    return PostTradeResult(
        as_of_date=as_of_date,
        previous_cash=previous_cash,
        new_cash=new_cash,
        orders_count=len(orders_list),
        position_sync=position_sync,
    )


__all__ = [
    "PostTradeResult",
    "apply_orders_and_persist",
]
