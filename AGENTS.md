# AI Agents & Prompts Guide

This document describes how tr(AI)ding's agents work, what context they receive, and how to extend their prompts. Future contributors can use it as the source of truth when evolving the AI layer.

## Agent System Overview
- **Weekly (Sunday) agent**: Performs macro / strategic review once per week. Its latest guidance is stored in `ai_weekly_research.md` and feeds the weekday agent.
- **Daily (weekday) agent**: Runs after market close, evaluates current portfolio data, and decides whether to trade. Prompt built in `app/prompts/prompts.py`.
- **Scheduler**: `app/schedule_runner.py` triggers `weekday_processing` or `sunday_processing` from `app/orchestrator.py` according to `WEEKDAY_AT` and `SUNDAY_AT` environment variables.

Both agents rely on portfolio data stored in SQLite (`db.sqlite3`). `app/data/collector.py` gathers the latest snapshots, while `app/data/inserter.py` keeps `stocks_info` updated with fresh market data.

## Data Inputs Provided to Agents
Weekday processing (`app/orchestrator.py:weekday_processing`) prepares the following payload for the prompt builder:

| Input              | Source helper                            | Notes |
|-------------------|-------------------------------------------|-------|
| Positions dataframe | `get_all_positions()` (`app/data/collector.py`) | Includes `date`, `ticker`, `qty`, `avg_price`. Latest tickers drive price fetching. |
| Latest cash dict  | `get_latest_cash()` (`collector.py`)      | Keys: `date`, `amount`, `total_portfolio_amount`. |
| Latest orders dataframe | `get_latest_orders()` (`collector.py`) | Returns all orders from the most recent trading date. |
| Weekly research dict | `get_latest_weekly_research()` (`collector.py`) | Pulls latest dated section from `ai_weekly_research.md`. |
| Market prices     | `get_stock_data()` + `insert_latest_daily_data()` | Fetches daily OHLCV data via yfinance, upserts into SQLite. |

The Sunday routine (`sunday_processing`) loads positions and writes market prices but does not send AI prompts by default. Extend it to contact a macro agent if needed.

## Prompt Construction
`Prompts.daily_ai_prompt(...)` builds the weekday agent instructions. Key sections:

1. **Role & Objective**: Defines the agent as a tactical portfolio manager, lists strategic goals, and reinforces alignment with the Sunday theory.
2. **Daily Inputs**: Enumerates tickers, cash snapshot, summary of the latest orders, and embeds plain-text tables of positions and same-day orders.
3. **Weekly Research Context**: Injects the full text of the most recent macro thesis.
4. **Constraints**: Hard rules (no leverage/derivatives, 25% max position, ≥10% cash, etc.) the agent must obey.
5. **Response Format**: Requires a daily summary, explicit action decision (maintain vs. trades), and justification.
6. **Safety Clauses**: Emphasizes no-trade option when warranted and mandates rebalancing suggestions when constraints are breached.

`Prompts.quick_test_prompt()` returns a small diagnostic prompt used for smoke tests.

### Prompt Variables & Formatting
- **Ticker universe**: Derived from unique tickers in positions; duplicates are removed.
- **Cash totals**: Provided as raw numbers. If unavailable, they may be `None`; prompts still render the keys.
- **Orders preview**: Up to 3 latest orders joined in a single line for quick reference.
- **Embedded tables**: Multi-line blocks injected directly into the prompt; ensure downstream models can handle the volume.
- **Weekly research date + text**: Inserted verbatim. Keep `ai_weekly_research.md` concise and clean to avoid prompt bloat.

When modifying prompt wording, prefer editing `Prompts.daily_ai_prompt` so all calling sites inherit the change.

## Orchestration Flow
1. `weekday_processing()` (or Sunday counterpart) loads the latest datasets and prints diagnostic information.
2. Weekday flow builds a prompt string via `Prompts.daily_ai_prompt` and sends it with `openai_integration.send_prompt()`.
3. `send_prompt()` (`app/openai_integration.py`) initializes the OpenAI client using `OPENAI_API_KEY`, optional `OPENAI_MODEL`/`OPENAI_BASE_URL`, and calls `client.responses.create(...)`.
4. The agent response text is printed to stdout; downstream automation can capture or persist it.

Configuration notes:
- Add secrets to `.env` in repo root. `python-dotenv` auto-loads them.
- Default model: `gpt-4o-mini`; override per-call via `send_prompt(..., model="...")`.
- Ensure `requirements.txt` includes `openai`, `yfinance`, `pandas`, `python-dotenv`.

## Extending or Adding Agents
1. **Create prompt builder**: Add a new `@staticmethod` in `Prompts` with clear sections, constraints, and response expectations.
2. **Update orchestrator**: Call the new builder from `weekday_processing`/`sunday_processing` or a new function, wiring in required data collectors.
3. **Persist context**: If additional data is required (e.g., risk metrics), extend `collector.py` and ensure the database schema and sync routines cover it.
4. **Document response contract**: Update this file and any runbooks so human reviewers understand what to expect from model outputs.
5. **Testing**: Use `Prompts.quick_test_prompt()` or craft a smaller sandbox prompt to validate SDK integration before deploying full prompts.

## Maintaining Weekly Guidance
- `ai_weekly_research.md` should be refreshed every Sunday with a new dated header.
- Keep sections short (1–3 paragraphs) and directly actionable. The latest section is fetched based on the most recent `YYYY-MM-DD` header.
- Archive older theories below; they remain for historical reference but are ignored by default.

## Troubleshooting Checklist
- **Missing API key**: `send_prompt` raises `RuntimeError`. Verify `.env`.
- **Empty datasets**: If positions/cash/orders are empty, prompts still render but agents may lack context. Check the corresponding SQLite tables and upstream data collectors.
- **Prompt too long**: Review positions/orders table size. Consider summarizing or truncating before embedding.
- **Scheduler drift**: Confirm server timezone and `WEEKDAY_AT`/`SUNDAY_AT`. Adjust in environment.

Use this guide when onboarding new models or iterating on prompt strategy to keep the AI layer consistent and reliable.
