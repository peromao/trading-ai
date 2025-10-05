import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
import pandas as pd

if (
    __package__ is None or __package__ == ""
):  # pragma: no cover - script execution fallback
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.collector import (
    get_all_positions,
    get_latest_cash,
    get_latest_cash_before,
    get_latest_orders,
    get_latest_weekly_research,
    get_portfolio,
)
from app.data.inserter import (
    insert_cash_snapshot,
    insert_new_order,
    sync_positions_with_portfolio,
)
from app.openai_integration import deep_research_async, send_prompt
from app.portfolio_manager import (
    CashSnapshot,
    apply_orders,
    compute_cash_after_orders,
)
from app.services.context_builder import build_market_context
from app.prompts.prompts import Prompts


def weekday_processing():
    """Processing routine for Monday–Friday.

    Reads tickers from env var `TICKERS` (comma-separated) or uses a small default list.
    Calls the data collector and returns the fetched data.
    """
    positions_df = get_all_positions()
    print(f"[weekday_processing] Loaded positions rows: {len(positions_df)}")

    market_ctx = build_market_context(positions_df)
    print(f"[weekday_processing] Fetched market data for tickers: {market_ctx.tickers}")
    print(
        f"[weekday_processing] Upserted {market_ctx.inserted_rows} rows into stocks_info (sqlite)"
    )

    latest_prices_df = market_ctx.latest_prices_df

    # Fetch latest cash info and all positions before sending the prompt
    latest_cash = get_latest_cash()
    weekly_research = get_latest_weekly_research()
    latest_orders = get_latest_orders()
    print(f"[weekday_processing] Latest cash: {latest_cash.get('amount')}")
    print(
        f"[weekday_processing] Weekly research date: {weekly_research.get('date_str','')}, chars: {len(weekly_research.get('text',''))}"
    )
    print(
        f"[weekday_processing] Latest orders rows: {0 if latest_orders is None else len(latest_orders)}"
    )

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


async def sunday_processing():
    """Processing routine for Sunday.

    Reads tickers from env var `SUNDAY_TICKERS` or falls back to `TICKERS`/default.
    Calls the data collector and returns the fetched data.
    """
    positions_df = get_all_positions()
    print(f"[sunday_processing] Loaded positions rows: {len(positions_df)}")

    market_ctx = build_market_context(positions_df)
    print(f"[sunday_processing] Fetched market data for tickers: {market_ctx.tickers}")
    print(
        f"[sunday_processing] Upserted {market_ctx.inserted_rows} rows into stocks_info (sqlite)"
    )

    latest_prices_df = market_ctx.latest_prices_df

    # Fetch latest cash info and all positions before sending the prompt
    latest_cash = get_latest_cash()
    weekly_research = get_latest_weekly_research()
    weekly_orders = get_latest_orders(start_date=date.today() - timedelta(days=7))
    print(f"[sunday_processing] Latest cash: {latest_cash.get('amount')}")
    print(
        f"[sunday_processing] Weekly research date: {weekly_research.get('date_str','')}, chars: {len(weekly_research.get('text',''))}"
    )
    print(
        f"[sunday_processing] Weekly orders rows: {0 if weekly_orders is None else len(weekly_orders)}"
    )

    prompt = Prompts.weekend_ai_prompt(
        positions_df=positions_df,
        latest_cash=latest_cash,
        weekly_orders=weekly_orders,
        latest_prices_df=latest_prices_df,
        weekly_research=weekly_research,
    )

    new_weekly_research = await deep_research_async(prompt)

    # Append the new weekly research to the markdown log with today's date header
    try:
        research_text = getattr(new_weekly_research, "research", "") or ""
        if research_text.strip():
            today_str = date.today().strftime("%Y-%m-%d")
            header_line = f"# {today_str}\n"
            # Ensure a clean separation from previous content and append section
            with open("ai_weekly_research.md", "a", encoding="utf-8") as f:
                f.write("\n" if not research_text.startswith("\n") else "")
                f.write(header_line)
                f.write("\n")
                f.write(research_text.rstrip())
                f.write("\n")
            print(
                f"[sunday_processing] Appended weekly research to ai_weekly_research.md with header {today_str}"
            )
        else:
            print(
                "[sunday_processing] No research text returned; skipping markdown update"
            )
    except Exception as e:
        print(f"[sunday_processing] Failed to append weekly research: {e}")
        return

    current_portfolio = get_portfolio()

    orders = new_weekly_research.orders

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
        f"[sunday_processing] Cash snapshot written for {as_of_date}: prev={prev_cash_val:.2f} -> new={new_cash_val:.2f}"
    )

    return


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
        asyncio.run(sunday_processing())


if __name__ == "__main__":
    main()
