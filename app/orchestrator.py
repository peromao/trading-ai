import argparse
from typing import List


def weekday_processing():
    """Processing routine for Monday–Friday.

    Reads tickers from env var `TICKERS` (comma-separated) or uses a small default list.
    Calls the data collector and returns the fetched data.
    """
    # Import locally to avoid issues when running as script vs module
    from data.collector import (
        get_stock_data,
        get_latest_cash,
        get_all_positions,
        get_latest_orders,
        get_latest_weekly_research,
    )
    from openai_integration import send_prompt

    # Load positions first and derive tickers from all rows
    positions_df = get_all_positions()
    tickers: List[str] = []
    if not positions_df.empty:
        seen = set()
        for t in positions_df.get("ticker", []).astype(str).tolist():
            if t and t not in seen:
                seen.add(t)
                tickers.append(t)
    if not tickers:
        tickers = ["AAPL", "MSFT", "GOOGL"]
    print(f"[weekday_processing] Fetching data for (latest positions): {tickers}")
    data = get_stock_data(tickers)
    print("[weekday_processing] Fetch complete; inserting into data/stocks_info.csv")
    # Persist the most recent daily row per ticker
    from data.inserter import insert_latest_daily_data

    inserted = insert_latest_daily_data(data, tickers, out_csv="data/stocks_info.csv")
    print(f"[weekday_processing] Inserted/updated {inserted} rows into stocks_info.csv")

    # Fetch latest cash info and all positions before sending the prompt
    latest_cash = get_latest_cash()
    weekly_research = get_latest_weekly_research()
    latest_orders = get_latest_orders()
    print(f"[weekday_processing] Latest cash: {latest_cash}")
    print(
        f"[weekday_processing] Weekly research date: {weekly_research.get('date_str','')}, chars: {len(weekly_research.get('text',''))}"
    )
    print(f"[weekday_processing] Latest orders rows: {0 if latest_orders is None else len(latest_orders)}")
    print(f"[weekday_processing] Loaded positions rows: {len(positions_df)}")

    # print(send_prompt("Qual a capital da bulgária?"))
    return data


def sunday_processing():
    """Processing routine for Sunday.

    Reads tickers from env var `SUNDAY_TICKERS` or falls back to `TICKERS`/default.
    Calls the data collector and returns the fetched data.
    """
    # Import locally to avoid issues when running as script vs module
    from data.collector import get_stock_data, get_all_positions

    positions_df = get_all_positions()
    tickers: List[str] = []
    if not positions_df.empty:
        seen = set()
        for t in positions_df.get("ticker", []).astype(str).tolist():
            if t and t not in seen:
                seen.add(t)
                tickers.append(t)
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
