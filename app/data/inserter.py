import os
from typing import List, Sequence

import pandas as pd


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
    """Insert the most recent daily row per ticker into a CSV.

    Parameters
    - daily_data: sequence of DataFrames as returned by `get_stock_data`,
                  in the same order as `tickers`. Each DataFrame should
                  include columns: Open, High, Low, Close, Volume, Dividends, Stock Splits.
    - tickers: sequence of ticker symbols corresponding to each DataFrame.
    - out_csv: target CSV file (default: data/prices.csv)

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
            "ticker": str(tkr).strip().strip("\"").strip("'"),
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

    new_df = pd.DataFrame.from_records(records)

    # Load existing file if present, then upsert on (date, ticker)
    if os.path.exists(out_csv) and os.path.getsize(out_csv) > 0:
        try:
            existing = pd.read_csv(out_csv, dtype={"ticker": str})
        except Exception:
            existing = pd.DataFrame()
    else:
        existing = pd.DataFrame()

    # Align columns with existing file if it exists; otherwise use default columns order
    if not existing.empty:
        # Add any missing columns to new_df
        for col in existing.columns:
            if col not in new_df.columns:
                new_df[col] = pd.NA
        # Reorder new_df to match existing
        new_df = new_df[existing.columns]
        merged = pd.concat([existing, new_df], ignore_index=True)
    else:
        # Choose a reasonable default column order
        preferred_cols = [
            "date",
            "ticker",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "dividends",
            "stock_splits",
        ]
        ordered = [c for c in preferred_cols if c in new_df.columns]
        ordered += [c for c in new_df.columns if c not in ordered]
        new_df = new_df[ordered]
        merged = new_df.copy()
    merged.drop_duplicates(subset=["date", "ticker"], keep="last", inplace=True)
    merged.sort_values(["date", "ticker"], inplace=True)

    _ensure_dir(out_csv)
    merged.to_csv(out_csv, index=False)
    return len(records)
