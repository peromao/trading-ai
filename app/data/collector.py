import yfinance as yf
import pandas as pd
from typing import List


def get_stock_data(stocksTickers: List[str]):
    dailyData = []

    for ticker in stocksTickers:
        dat = yf.Ticker(ticker)
        dailyData.append(dat.history(period="1d"))

    return dailyData


def _clean_ticker(t: str) -> str:
    # Remove stray quotes and whitespace from CSV values
    return t.strip().strip('"').strip("'")


def get_portfolio_tickers(positions_path: str = "data/positions.csv") -> List[str]:
    """Return unique tickers from the most recent date in positions.csv.

    Handles weekend gaps by simply selecting the max 'date' present in the file.
    """
    df = pd.read_csv(positions_path, parse_dates=["date"])
    if df.empty:
        return []
    latest_date = df["date"].max()
    latest = df[df["date"] == latest_date]
    tickers = [
        _clean_ticker(t)
        for t in latest["ticker"].astype(str).tolist()
        if str(t).strip()
    ]
    # Preserve order while deduping
    seen = set()
    unique = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique
