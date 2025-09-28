import argparse
from typing import Iterable, List, Optional, Sequence

import pandas as pd


def build_latest_prices_df(
    price_frames: Sequence[Optional[pd.DataFrame]],
    tickers: Iterable[str],
) -> pd.DataFrame:
    """Return a dataframe containing the latest OHLCV row for each ticker."""

    latest_price_rows = []
    for tkr, df in zip(tickers, price_frames):
        if df is None or getattr(df, "empty", True):
            continue
        try:
            last_idx = df.index[-1]
            row = df.iloc[-1]
        except Exception:
            continue

        ts = pd.Timestamp(last_idx)
        try:
            date_str = ts.date().isoformat()
        except Exception:
            date_str = str(ts)

        def _safe_float(val):
            return None if val is None or pd.isna(val) else float(val)

        volume_val = row.get("Volume")
        if volume_val is None or pd.isna(volume_val):
            volume = None
        else:
            volume = int(volume_val)

        latest_price_rows.append(
            {
                "date": date_str,
                "ticker": str(tkr).strip(),
                "open": _safe_float(row.get("Open")),
                "high": _safe_float(row.get("High")),
                "low": _safe_float(row.get("Low")),
                "close": _safe_float(row.get("Close")),
                "volume": volume,
            }
        )

    return pd.DataFrame(latest_price_rows) if latest_price_rows else pd.DataFrame()


def weekday_processing():
    """Processing routine for Monday–Friday.

    Reads tickers from env var `TICKERS` (comma-separated) or uses a small default list.
    Calls the data collector and returns the fetched data.
    """
    # Import locally to avoid issues when running as script vs module
    from data.collector import (
        get_stock_data,
        get_latest_cash,
        get_latest_cash_before,
        get_all_positions,
        get_latest_orders,
        get_latest_weekly_research,
        get_portfolio,
    )
    from openai_integration import send_prompt
    from prompts.prompts import Prompts

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
    print("[weekday_processing] Fetch complete; inserting into sqlite: stocks_info")
    # Persist the most recent daily row per ticker
    from data.inserter import (
        insert_latest_daily_data,
        insert_new_order,
        sync_positions_with_portfolio,
        insert_cash_snapshot,
    )

    inserted = insert_latest_daily_data(data, tickers, out_csv="data/stocks_info.csv")
    print(f"[weekday_processing] Upserted {inserted} rows into stocks_info (sqlite)")

    latest_prices_df = build_latest_prices_df(data, tickers)

    # Fetch latest cash info and all positions before sending the prompt
    latest_cash = get_latest_cash()
    weekly_research = get_latest_weekly_research()
    latest_orders = get_latest_orders()
    print(f"[weekday_processing] Latest cash: {latest_cash.get("amount")}")
    print(
        f"[weekday_processing] Weekly research date: {weekly_research.get('date_str','')}, chars: {len(weekly_research.get('text',''))}"
    )
    print(
        f"[weekday_processing] Latest orders rows: {0 if latest_orders is None else len(latest_orders)}"
    )
    print(f"[weekday_processing] Loaded positions rows: {len(positions_df)}")

    # Build and send the daily AI prompt
    prompt_text = Prompts.daily_ai_prompt(
        positions_df=positions_df,
        latest_cash=latest_cash,
        latest_orders=latest_orders,
        weekly_research=weekly_research,
        latest_prices_df=latest_prices_df,
    )
    ai_decision = send_prompt(prompt_text)

    orders = ai_decision.orders

    if len(orders) != 0:
        print(f"[weekday_processing] Inserting {len(orders)} orders")
        for order in orders:
            insert_new_order(order)
            print(f"[weekday_processing] Order inserted: {order}")
    else:
        print(f"[weekday_processing] No orders for today")
        return

    current_portfolio = get_portfolio()

    from portfolio_manager import (
        apply_orders,
        compute_cash_after_orders,
        CashSnapshot,
    )

    new_portfolio = apply_orders(current_portfolio, orders)

    sync_positions_with_portfolio(new_portfolio)

    as_of_date = pd.Timestamp.utcnow().date()
    prior_cash = get_latest_cash_before(as_of_date)
    prev_amount = prior_cash.get("amount") if prior_cash else None
    prev_cash_val = (
        0.0 if prev_amount is None or pd.isna(prev_amount) else float(prev_amount)
    )

    new_cash_val = compute_cash_after_orders(prev_cash_val, orders)

    snapshot = CashSnapshot(
        date=as_of_date, amount=new_cash_val, total_portfolio_amount=None
    )
    insert_cash_snapshot(snapshot)
    print(
        f"[weekday_processing] Cash snapshot written for {as_of_date}: prev={prev_cash_val:.2f} -> new={new_cash_val:.2f}"
    )

    return


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
    print("[sunday_processing] Fetch complete; inserting into sqlite: stocks_info")
    # Persist the most recent daily row per ticker
    from data.inserter import insert_latest_daily_data

    inserted = insert_latest_daily_data(data, tickers, out_csv="data/stocks_info.csv")
    print(f"[sunday_processing] Upserted {inserted} rows into stocks_info (sqlite)")
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
