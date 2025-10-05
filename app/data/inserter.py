import math
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
from data.db import bootstrap_db, get_connection

from domain.models import Order
from portfolio_manager import Portfolio, CashSnapshot

def _to_date_str(ts) -> str:
    ts = pd.to_datetime(ts)
    # Keep calendar day; ignore timezone for formatting
    return ts.date().strftime("%Y-%m-%d")


def insert_latest_daily_data(
    daily_data: Sequence[pd.DataFrame],
    tickers: Sequence[str],
):
    """Insert the most recent daily row per ticker into SQLite (stocks_info).

    Parameters
    - daily_data: sequence of DataFrames as returned by `get_stock_data`,
                  in the same order as `tickers`. Each DataFrame should
                  include columns: Open, High, Low, Close, Volume, Dividends, Stock Splits.
    - tickers: sequence of ticker symbols corresponding to each DataFrame.

    Behavior
    - Extracts the most recent row from each DataFrame.
    - Normalizes the date to yyyy-mm-dd.
    - Upserts rows into SQLite `stocks_info` keyed by (date, ticker).
    """
    if len(daily_data) != len(tickers):
        raise ValueError("daily_data and tickers must have the same length")

    records = []
    for tkr, df in zip(tickers, daily_data):
        if df is None or df.empty:
            continue
        # Take most recent row
        last_idx = df.index[-1]
        row = df.iloc[-1]
        record = {
            "date": _to_date_str(last_idx),
            "ticker": str(tkr).strip().strip('"').strip("'"),
            "open": float(row.get("Open")),
            "high": float(row.get("High")),
            "low": float(row.get("Low")),
            "close": float(row.get("Close")),
            "volume": int(row.get("Volume")),
        }
        # If dividends/splits are present, include them; otherwise they'll be omitted
        if "Dividends" in row.index:
            record["dividends"] = float(row.get("Dividends", 0.0))
        if "Stock Splits" in row.index:
            record["stock_splits"] = float(row.get("Stock Splits", 0.0))
        records.append(record)

    if not records:
        return 0

    # Insert records into SQLite with upsert semantics
    bootstrap_db()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO stocks_info(
                date, ticker, open, high, low, close, volume, dividends, stock_splits
            ) VALUES (:date, :ticker, :open, :high, :low, :close, :volume, :dividends, :stock_splits)
            ON CONFLICT(date, ticker) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                dividends=COALESCE(excluded.dividends, stocks_info.dividends),
                stock_splits=COALESCE(excluded.stock_splits, stocks_info.stock_splits)
            """,
            records,
        )
        conn.commit()
    finally:
        conn.close()
    return len(records)


def insert_new_order(order: Order):
    """Append a single executed order into SQLite `orders`.

    The `date` stored is today's calendar date (YYYY-MM-DD, UTC-based).

    Returns the inserted row id.
    """
    if order is None:
        raise ValueError("order must not be None")

    # Normalize fields
    ticker = str(order.ticker).strip().strip('"').strip("'")
    if not ticker:
        raise ValueError("order.ticker must be a non-empty string")

    qty = int(order.qty)
    price = float(order.price)

    # Use current date (ignore time component)
    date_str = _to_date_str(pd.Timestamp.utcnow())

    # Insert into SQLite
    bootstrap_db()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders(date, ticker, qty, price) VALUES (?, ?, ?, ?)",
            (date_str, ticker, qty, price),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _float_equal(a: Optional[float], b: Optional[float], *, tol: float = 1e-9) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)
    except (TypeError, ValueError):
        return False


def sync_positions_with_portfolio(
    portfolio: Portfolio,
    *,
    as_of: Optional[Any] = None,
) -> Dict[str, int]:
    """Sync the SQLite `positions` table with the provided portfolio snapshot.

    Args:
        portfolio: Current portfolio holdings.
        as_of: Optional date override (str/date/datetime). Used when writing new or
            changed rows. Defaults to UTC now if not provided and the position
            instance lacks a date.

    Returns:
        Dict with counts of inserted, updated, and deleted rows.
    """

    default_date_str = _to_date_str(as_of or pd.Timestamp.utcnow())

    bootstrap_db()
    conn = get_connection()
    inserted = updated = deleted = 0

    try:
        cur = conn.cursor()

        # Load existing rows keyed by ticker, keeping the most recent entry.
        rows = cur.execute(
            "SELECT rowid as rowid, date, ticker, qty, avg_price FROM positions"
        ).fetchall()

        existing_by_ticker: Dict[str, Dict[str, Any]] = {}
        duplicate_rowids: List[int] = []

        for row in rows:
            ticker = str(row["ticker"])
            if not ticker:
                continue

            current = existing_by_ticker.get(ticker)
            current_date = row["date"] or ""

            if current is None:
                existing_by_ticker[ticker] = {
                    "rowid": row["rowid"],
                    "date": row["date"],
                    "qty": row["qty"],
                    "avg_price": row["avg_price"],
                }
                continue

            stored_date = current["date"] or ""

            if current_date > stored_date or (
                current_date == stored_date and row["rowid"] > current["rowid"]
            ):
                duplicate_rowids.append(current["rowid"])
                existing_by_ticker[ticker] = {
                    "rowid": row["rowid"],
                    "date": row["date"],
                    "qty": row["qty"],
                    "avg_price": row["avg_price"],
                }
            else:
                duplicate_rowids.append(row["rowid"])

        # Remove duplicates so only one row per ticker remains.
        for rowid in duplicate_rowids:
            cur.execute("DELETE FROM positions WHERE rowid = ?", (rowid,))
            deleted += cur.rowcount

        # Compute target positions keyed by ticker.
        target_positions: Dict[str, Any] = {}
        for position in portfolio.positions:
            ticker = str(position.ticker)
            if not ticker:
                continue
            target_positions[ticker] = position

        existing_tickers = set(existing_by_ticker.keys())
        target_tickers = set(target_positions.keys())

        # Remove tickers no longer present in the portfolio.
        for ticker in existing_tickers - target_tickers:
            cur.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
            deleted += cur.rowcount
            existing_by_ticker.pop(ticker, None)

        # Upsert the remaining tickers.
        for ticker, position in target_positions.items():
            qty = None if position.qty is None else float(position.qty)
            avg_price = (
                None if position.avg_price is None else float(position.avg_price)
            )

            if position.date is not None:
                desired_date = _to_date_str(position.date)
            else:
                desired_date = default_date_str

            existing = existing_by_ticker.get(ticker)

            if existing is None:
                cur.execute(
                    "INSERT INTO positions(date, ticker, qty, avg_price) VALUES (?, ?, ?, ?)",
                    (desired_date, ticker, qty, avg_price),
                )
                inserted += 1
                continue

            same_qty = _float_equal(existing["qty"], qty)
            same_avg = _float_equal(existing["avg_price"], avg_price)
            same_date = (existing["date"] or "") == desired_date

            if same_qty and same_avg and same_date:
                continue

            cur.execute(
                "UPDATE positions SET date = ?, qty = ?, avg_price = ? WHERE rowid = ?",
                (desired_date, qty, avg_price, existing["rowid"]),
            )
            updated += cur.rowcount

        conn.commit()
    finally:
        conn.close()

    return {"inserted": inserted, "updated": updated, "deleted": deleted}


def insert_cash_snapshot(snapshot: CashSnapshot) -> None:
    """Insert or replace a cash snapshot row in SQLite `cash`.

    This function performs no business logic: it simply writes the provided
    snapshot (date, amount, total_portfolio_amount) using upsert semantics.
    """
    if snapshot is None:
        raise ValueError("snapshot must not be None")

    if snapshot.date is None:
        raise ValueError("snapshot.date must not be None")

    bootstrap_db()
    conn = get_connection()
    try:
        # Normalize date to yyyy-mm-dd
        date_str = _to_date_str(snapshot.date)
        amount = float(snapshot.amount)
        total = (
            None
            if snapshot.total_portfolio_amount is None
            else float(snapshot.total_portfolio_amount)
        )

        conn.execute(
            """
            INSERT INTO cash(date, amount, total_portfolio_amount)
            VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                amount = excluded.amount,
                total_portfolio_amount = excluded.total_portfolio_amount
            """,
            (date_str, amount, total),
        )
        conn.commit()
    finally:
        conn.close()
