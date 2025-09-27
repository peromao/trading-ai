from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Tuple


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
