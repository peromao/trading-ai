import os
from typing import List, Sequence

import pandas as pd
from data.db import bootstrap_db, get_connection

from openai_integration import Order


def _ensure_dir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _to_date_str(ts) -> str:
    ts = pd.to_datetime(ts)
    # Keep calendar day; ignore timezone for formatting
    return ts.date().strftime("%Y-%m-%d")


def insert_latest_daily_data(
    daily_data: Sequence[pd.DataFrame],
    tickers: Sequence[str],
    out_csv: str = "data/stocks_info.csv",
):
    """Insert the most recent daily row per ticker into SQLite (stocks_info).

    Parameters
    - daily_data: sequence of DataFrames as returned by `get_stock_data`,
                  in the same order as `tickers`. Each DataFrame should
                  include columns: Open, High, Low, Close, Volume, Dividends, Stock Splits.
    - tickers: sequence of ticker symbols corresponding to each DataFrame.
    - out_csv: deprecated (no longer used; kept for backward-compat)

    Behavior
    - Extracts the most recent row from each DataFrame.
    - Normalizes the date to yyyy-mm-dd.
    - Appends to `out_csv`, upserting on (date, ticker) to avoid duplicates.
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
