import os
import argparse
from typing import List


def _get_tickers(env_var: str, default: List[str]) -> List[str]:
    raw = os.getenv(env_var, "")
    if raw.strip():
        return [t.strip() for t in raw.split(",") if t.strip()]
    return default


def weekday_processing():
    """Processing routine for Monday–Friday.

    Reads tickers from env var `TICKERS` (comma-separated) or uses a small default list.
    Calls the data collector and returns the fetched data.
    """
    # Import locally to avoid issues when running as script vs module
    from data.collector import get_stock_data, get_portfolio_tickers

    # Prefer tickers from latest positions; allow env override for quick tests
    tickers = _get_tickers("TICKERS", []) or get_portfolio_tickers()
    if not tickers:
        tickers = ["AAPL", "MSFT", "GOOGL"]
    print(f"[weekday_processing] Fetching data for (latest positions): {tickers}")
    data = get_stock_data(tickers)
    print("[weekday_processing] Fetch complete; inserting into data/stocks_info.csv")
    # Persist the most recent daily row per ticker
    from data.inserter import insert_latest_daily_data

    inserted = insert_latest_daily_data(data, tickers, out_csv="data/stocks_info.csv")
    print(f"[weekday_processing] Inserted/updated {inserted} rows into stocks_info.csv")
    return data


def sunday_processing():
    """Processing routine for Sunday.

    Reads tickers from env var `SUNDAY_TICKERS` or falls back to `TICKERS`/default.
    Calls the data collector and returns the fetched data.
    """
    # Import locally to avoid issues when running as script vs module
    from data.collector import get_stock_data, get_portfolio_tickers

    tickers = (
        _get_tickers("SUNDAY_TICKERS", [])
        or _get_tickers("TICKERS", [])
        or get_portfolio_tickers()
    )
    if not tickers:
        tickers = ["AAPL", "MSFT", "GOOGL"]
    print(f"[sunday_processing] Fetching data for (latest positions): {tickers}")
    data = get_stock_data(tickers)
    print("[sunday_processing] Fetch complete; inserting into data/stocks_info.csv")
    # Persist the most recent daily row per ticker
    from data.inserter import insert_latest_daily_data

    inserted = insert_latest_daily_data(data, tickers, out_csv="data/stocks_info.csv")
    print(f"[sunday_processing] Inserted/updated {inserted} rows into stocks_info.csv")
    return data


def main(argv=None):
    """CLI entry to test processing.

    Examples:
      - python app/orchestrator.py --run weekday
      - python -m app.orchestrator --run weekday
    """
    parser = argparse.ArgumentParser(description="Run orchestrator processing routines")
    parser.add_argument(
        "--run",
        choices=["weekday", "sunday"],
        default="weekday",
        help="Which processing routine to execute (default: weekday)",
    )
    args = parser.parse_args(argv)

    if args.run == "weekday":
        weekday_processing()
    else:
        sunday_processing()


if __name__ == "__main__":
    main()
