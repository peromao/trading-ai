import yfinance as yf
import pandas as pd
from typing import List, Dict, Any


def get_stock_data(stocksTickers: List[str]):
    dailyData = []

    for ticker in stocksTickers:
        dat = yf.Ticker(ticker)
        dailyData.append(dat.history(period="1d"))

    return dailyData


def _clean_ticker(t: str) -> str:
    # Remove stray quotes and whitespace from CSV values
    return t.strip().strip('"').strip("'")


## Removed: get_portfolio_tickers. Use get_all_positions() and filter by latest date in orchestrator.


def get_latest_cash(cash_path: str = "data/cash.csv") -> Dict[str, Any]:
    """Return the latest cash information from cash.csv.

    - Normalizes header names by stripping spaces.
    - Parses the `date` column as datetime.
    - Returns a dict with keys: `date`, `amount`, `total_portfolio_amount`.
    """
    df = pd.read_csv(cash_path)
    # Normalize headers (handle "date, amount, total_portfolio_amount")
    df.columns = [c.strip() for c in df.columns]
    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df.empty:
        return {"date": None, "amount": None, "total_portfolio_amount": None}
    latest_idx = df["date"].idxmax()
    row = df.loc[latest_idx]
    return {
        "date": row["date"],
        "amount": row.get("amount"),
        "total_portfolio_amount": row.get("total_portfolio_amount"),
    }


def get_all_positions(positions_path: str = "data/positions.csv") -> pd.DataFrame:
    """Load and return the full positions dataset with cleaned columns.

    - Parses `date` as datetime
    - Strips whitespace from headers
    - Cleans ticker values (removes quotes/whitespace)
    """
    df = pd.read_csv(positions_path)
    # Normalize headers
    df.columns = [c.strip() for c in df.columns]
    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).map(_clean_ticker)
    return df


def get_latest_orders(orders_path: str = "data/orders.csv") -> pd.DataFrame:
    """Return all order rows from the latest date in orders.csv.

    - Normalizes header names by stripping spaces
    - Parses `date` as datetime
    - Cleans `ticker` values (removes quotes/whitespace)
    - Returns a DataFrame filtered to rows with max(date)
    """
    df = pd.read_csv(orders_path)
    # Normalize headers
    df.columns = [c.strip() for c in df.columns]
    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).map(_clean_ticker)
    if df.empty or "date" not in df.columns:
        return df
    latest_date = df["date"].max()
    return df[df["date"] == latest_date].copy()
