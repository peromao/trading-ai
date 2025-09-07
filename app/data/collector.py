import yfinance as yf
import pandas as pd
import re
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime


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


def get_latest_weekly_research(research_path: str = "ai_weekly_research.md") -> Dict[str, Any]:
    """Parse the weekly research Markdown and return the most recent section.

    The file is expected to contain sections starting with a Markdown header
    (one or more '#') that includes a date like YYYY-MM-DD. The content for a
    given date runs until the next dated header or the end of file.

    Returns a dict with keys:
      - date: datetime (if parsed) or None
      - date_str: the YYYY-MM-DD string (if found) or ""
      - text: the concatenated text content (str)
    """
    try:
        with open(research_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return {"date": None, "date_str": "", "text": ""}

    header_indices: List[Tuple[int, str]] = []  # (line_index, date_str)
    date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})")

    for idx, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("#"):
            m = date_pattern.search(line)
            if m:
                header_indices.append((idx, m.group(1)))

    if not header_indices:
        return {"date": None, "date_str": "", "text": ""}

    # Pick the header with the max date value
    def parse_date(s: str) -> datetime:
        return datetime.strptime(s, "%Y-%m-%d")

    latest_idx, latest_date_str = max(
        header_indices, key=lambda t: parse_date(t[1])
    )

    # Content is from next line after latest_idx until the next dated header or EOF
    next_headers = [i for i, _ in header_indices if i > latest_idx]
    end_idx = min(next_headers) if next_headers else len(lines)
    content_lines = lines[latest_idx + 1 : end_idx]
    text = "".join(content_lines).strip()

    latest_date = None
    try:
        latest_date = parse_date(latest_date_str)
    except Exception:
        pass

    return {"date": latest_date, "date_str": latest_date_str, "text": text}
