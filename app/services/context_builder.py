"""Helpers to assemble shared market context for orchestrator flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import pandas as pd

from app.data.collector import get_stock_data
from app.data.inserter import insert_latest_daily_data

DEFAULT_FALLBACK_TICKERS: Sequence[str] = ("AAPL", "MSFT", "GOOGL")


@dataclass(frozen=True)
class MarketContext:
    """Bundle of market inputs shared by weekday and weekend flows."""

    tickers: list[str]
    price_frames: Sequence[Optional[pd.DataFrame]]
    latest_prices_df: pd.DataFrame
    inserted_rows: int


def select_tickers(
    positions_df: Optional[pd.DataFrame],
    *,
    fallback: Optional[Sequence[str]] = None,
) -> list[str]:
    """Return the deduplicated ticker universe or a fallback list.

    The fallback defaults to :data:`DEFAULT_FALLBACK_TICKERS` when no tickers are
    present in the positions dataframe. Leading/trailing whitespace is stripped.
    """

    tickers: list[str] = []

    if positions_df is not None and not positions_df.empty and "ticker" in positions_df:
        seen: set[str] = set()
        for raw in positions_df.get("ticker", []).astype(str).tolist():
            value = raw.strip()
            if value and value not in seen:
                seen.add(value)
                tickers.append(value)

    if not tickers:
        fallback_values = fallback or DEFAULT_FALLBACK_TICKERS
        tickers = [str(t).strip() for t in fallback_values if str(t).strip()]

    return tickers


def build_latest_prices_df(
    price_frames: Sequence[Optional[pd.DataFrame]],
    tickers: Sequence[str],
) -> pd.DataFrame:
    """Return a dataframe containing the latest OHLCV row for each ticker."""

    latest_price_rows: list[dict[str, object]] = []
    for tkr, df in zip(tickers, price_frames):
        if df is None or getattr(df, "empty", True):
            continue
        try:
            last_idx = df.index[-1]
            row = df.iloc[-1]
        except Exception:
            continue

        ts = pd.Timestamp(last_idx)
        try:
            date_str = ts.date().isoformat()
        except Exception:
            date_str = str(ts)

        def _safe_float(val: object) -> Optional[float]:
            return None if val is None or pd.isna(val) else float(val)

        volume_val = row.get("Volume")
        if volume_val is None or pd.isna(volume_val):
            volume = None
        else:
            volume = int(volume_val)

        latest_price_rows.append(
            {
                "date": date_str,
                "ticker": str(tkr).strip(),
                "open": _safe_float(row.get("Open")),
                "high": _safe_float(row.get("High")),
                "low": _safe_float(row.get("Low")),
                "close": _safe_float(row.get("Close")),
                "volume": volume,
            }
        )

    return pd.DataFrame(latest_price_rows) if latest_price_rows else pd.DataFrame()


def build_market_context(
    positions_df: Optional[pd.DataFrame],
    *,
    fallback_tickers: Optional[Sequence[str]] = None,
) -> MarketContext:
    """Compose tickers, price frames, and latest-price snapshot for prompts."""

    tickers = select_tickers(positions_df, fallback=fallback_tickers)
    price_frames = get_stock_data(tickers)
    inserted_rows = insert_latest_daily_data(price_frames, tickers)
    latest_prices_df = build_latest_prices_df(price_frames, tickers)
    return MarketContext(
        tickers=list(tickers),
        price_frames=price_frames,
        latest_prices_df=latest_prices_df,
        inserted_rows=inserted_rows,
    )


__all__ = [
    "DEFAULT_FALLBACK_TICKERS",
    "MarketContext",
    "build_latest_prices_df",
    "build_market_context",
    "select_tickers",
]
