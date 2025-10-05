import argparse
import asyncio
import os
import sys
from datetime import date, timedelta

if (
    __package__ is None or __package__ == ""
):  # pragma: no cover - script execution fallback
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.collector import (
    get_all_positions,
    get_latest_cash,
    get_latest_orders,
    get_latest_weekly_research,
)
from app.data.inserter import insert_new_order
from app.openai_integration import deep_research_async, send_prompt
from app.services.context_builder import build_market_context
from app.services.post_trade import apply_orders_and_persist
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

    if not orders:
        print(f"[weekday_processing] No orders for today")
        return

    print(f"[weekday_processing] Inserting {len(orders)} orders")
    for order in orders:
        insert_new_order(order)
        print(f"[weekday_processing] Order inserted: {order}")

    post_trade = apply_orders_and_persist(orders)
    print(
        f"[weekday_processing] Cash snapshot written for {post_trade.as_of_date}: prev={post_trade.previous_cash:.2f} -> new={post_trade.new_cash:.2f}"
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

    orders = new_weekly_research.orders

    post_trade = apply_orders_and_persist(orders)
    print(
        f"[sunday_processing] Cash snapshot written for {post_trade.as_of_date}: prev={post_trade.previous_cash:.2f} -> new={post_trade.new_cash:.2f}"
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
