import pandas as pd
import re
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta

from data.db import bootstrap_db, df_from_query
from portfolio_manager import Portfolio, PortfolioPosition


def get_stock_data(stocksTickers: List[str]):
    import yfinance as yf  # imported here to avoid dependency for other helpers
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
    """Return the latest cash information from SQLite.

    Returns a dict with keys: `date`, `amount`, `total_portfolio_amount`.
    """
    bootstrap_db()
    df = df_from_query(
        "SELECT date, amount, total_portfolio_amount FROM cash ORDER BY date DESC LIMIT 1"
    )
    if df.empty:
        return {"date": None, "amount": None, "total_portfolio_amount": None}
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    row = df.iloc[0]
    return {
        "date": row["date"],
        "amount": row.get("amount"),
        "total_portfolio_amount": row.get("total_portfolio_amount"),
    }


def get_latest_cash_before(as_of) -> Dict[str, Any]:
    """Return the latest cash row strictly before a given date.

    Args:
        as_of: str/date/datetime. Rows with date < as_of are eligible.
    Returns dict with keys: `date`, `amount`, `total_portfolio_amount`, or
    all None if none exists.
    """
    bootstrap_db()
    try:
        as_of_dt = pd.to_datetime(as_of, errors="coerce")
    except Exception:
        as_of_dt = pd.NaT
    if pd.isna(as_of_dt):
        return {"date": None, "amount": None, "total_portfolio_amount": None}

    as_of_str = as_of_dt.date().strftime("%Y-%m-%d")
    df = df_from_query(
        "SELECT date, amount, total_portfolio_amount FROM cash WHERE date < ? ORDER BY date DESC LIMIT 1",
        params=[as_of_str],
    )
    if df.empty:
        return {"date": None, "amount": None, "total_portfolio_amount": None}
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    row = df.iloc[0]
    return {
        "date": row["date"],
        "amount": row.get("amount"),
        "total_portfolio_amount": row.get("total_portfolio_amount"),
    }


def get_all_positions(positions_path: str = "data/positions.csv") -> pd.DataFrame:
    """Load and return the full positions dataset from SQLite."""
    bootstrap_db()
    df = df_from_query("SELECT date, ticker, qty, avg_price FROM positions")
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if "ticker" in df.columns:
            df["ticker"] = df["ticker"].astype(str).map(_clean_ticker)
    return df


def get_latest_orders(start_date: Optional[Any] = None, orders_path: str = "data/orders.csv") -> pd.DataFrame:
    """Return order rows for yesterday or orders on/after a given date.

    Args:
        start_date: Optional date (str/datetime). If provided, returns all rows
            with `date` >= start_date. If omitted, returns rows for yesterday's
            calendar date.
        orders_path: Unused CSV fallback kept for compatibility.
    """
    bootstrap_db()
    query: str
    params: List[Any] = []

    if start_date is None:
        target_date = (datetime.now().date() - timedelta(days=1)).strftime("%Y-%m-%d")
        query = (
            """
            SELECT date, ticker, qty, price
            FROM orders
            WHERE date = ?
            ORDER BY rowid
            """
        )
        params = [target_date]
    else:
        start_dt = pd.to_datetime(start_date, errors="coerce")
        if pd.isna(start_dt):
            return pd.DataFrame(columns=["date", "ticker", "qty", "price"])
        start_str = start_dt.strftime("%Y-%m-%d")
        query = (
            """
            SELECT date, ticker, qty, price
            FROM orders
            WHERE date >= ?
            ORDER BY date, rowid
            """
        )
        params = [start_str]

    df = df_from_query(query, params=params)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).map(_clean_ticker)
    return df


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


def get_portfolio() -> Portfolio:
    """Return the full positions dataset as a Portfolio instance."""
    positions_df = get_all_positions()
    if positions_df.empty:
        return Portfolio.from_rows([])

    records = positions_df.to_dict(orient="records")
    positions: List[PortfolioPosition] = []
    for row in records:
        raw_date = row.get("date")
        if pd.isna(raw_date):
            parsed_date = None
        else:
            ts = pd.to_datetime(raw_date, errors="coerce")
            parsed_date = ts.date() if not pd.isna(ts) else None

        ticker = str(row.get("ticker", "")).strip().strip('"').strip("'")
        qty = row.get("qty")
        avg_price = row.get("avg_price")

        positions.append(
            PortfolioPosition(
                date=parsed_date,
                ticker=ticker,
                qty=None if qty is None or pd.isna(qty) else float(qty),
                avg_price=None if avg_price is None or pd.isna(avg_price) else float(avg_price),
            )
        )

    return Portfolio.from_rows(positions)
