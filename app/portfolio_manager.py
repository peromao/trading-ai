from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Tuple

from openai_integration import Order


@dataclass(frozen=True)
class PortfolioPosition:
    date: Optional[date]
    ticker: str
    qty: Optional[float]
    avg_price: Optional[float]


@dataclass(frozen=True)
class Portfolio:
    positions: Tuple[PortfolioPosition, ...]

    @classmethod
    def from_rows(cls, rows: Iterable[PortfolioPosition]) -> "Portfolio":
        return cls(tuple(rows))


@dataclass(frozen=True)
class CashSnapshot:
    """Represents a cash balance snapshot for a given date.

    - date: calendar day for the snapshot
    - amount: uninvested cash balance at end of the day
    - total_portfolio_amount: optional total portfolio value for the day
      (leave as None if you don't compute it elsewhere)
    """

    date: date
    amount: float
    total_portfolio_amount: Optional[float] = None


def apply_orders(portfolio: Portfolio, orders: Iterable[Order]) -> Portfolio:
    """Apply executed orders to the current portfolio and return the updated state."""

    positions_by_ticker: dict[str, PortfolioPosition] = {}
    for position in portfolio.positions:
        key = position.ticker
        if key:
            positions_by_ticker[str(key)] = position

    for order in orders:
        ticker_key = str(order.ticker)
        if not ticker_key:
            raise ValueError("Order ticker must be a non-empty string")

        delta_qty = float(order.qty)
        if delta_qty == 0:
            continue

        price = float(order.price)

        existing = positions_by_ticker.get(ticker_key)

        if existing is None:
            if delta_qty < 0:
                raise ValueError(
                    f"Cannot sell ticker '{ticker_key}' that is not in the portfolio"
                )
            positions_by_ticker[ticker_key] = PortfolioPosition(
                date=None,
                ticker=ticker_key,
                qty=delta_qty,
                avg_price=price,
            )
            continue

        existing_qty = float(existing.qty) if existing.qty is not None else 0.0
        existing_avg_price = (
            float(existing.avg_price) if existing.avg_price is not None else 0.0
        )

        new_qty = existing_qty + delta_qty

        if delta_qty < 0 and existing_qty + delta_qty < -1e-9:
            raise ValueError(
                f"Order would reduce '{ticker_key}' below zero (have {existing_qty}, delta {delta_qty})"
            )

        if abs(new_qty) < 1e-9:
            positions_by_ticker.pop(ticker_key, None)
            continue

        if new_qty < 0:
            raise ValueError(
                f"Invalid resulting quantity {new_qty} for ticker '{ticker_key}'"
            )

        if delta_qty > 0:
            total_cost = existing_qty * existing_avg_price + delta_qty * price
            new_avg_price = total_cost / new_qty if new_qty else price
        else:
            new_avg_price = existing.avg_price

        positions_by_ticker[ticker_key] = PortfolioPosition(
            date=existing.date,
            ticker=existing.ticker,
            qty=new_qty,
            avg_price=new_avg_price,
        )

    updated_positions = sorted(positions_by_ticker.values(), key=lambda pos: pos.ticker)
    return Portfolio.from_rows(updated_positions)


def compute_cash_after_orders(prev_cash: float, orders: Iterable[Order]) -> float:
    """Compute end-of-day cash from previous cash and executed orders.

    Sign convention (matches Order):
      - qty > 0 (buy) consumes cash: delta = -qty * price
      - qty < 0 (sell) adds cash:   delta = -qty * price

    No fees are applied.
    """
    delta = 0.0
    for o in orders or []:
        # Ensure numeric types
        q = float(o.qty)
        p = float(o.price)
        delta += -(q * p)
    return float(prev_cash) + delta
