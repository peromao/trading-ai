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
    from data.collector import get_stock_data

    tickers = _get_tickers("TICKERS", ["AAPL", "MSFT", "GOOGL"])
    print(f"[weekday_processing] Fetching data for: {tickers}")
    data = get_stock_data(tickers)
    print("[weekday_processing] Fetch complete")
    return data


def sunday_processing():
    """Processing routine for Sunday.

    Reads tickers from env var `SUNDAY_TICKERS` or falls back to `TICKERS`/default.
    Calls the data collector and returns the fetched data.
    """
    # Import locally to avoid issues when running as script vs module
    from app.data.collector import get_stock_data

    tickers = _get_tickers(
        "SUNDAY_TICKERS", _get_tickers("TICKERS", ["AAPL", "MSFT", "GOOGL"])
    )
    print(f"[sunday_processing] Fetching data for: {tickers}")
    data = get_stock_data(tickers)
    print("[sunday_processing] Fetch complete")
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
