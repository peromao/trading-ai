# AI Agents & Prompts Guide

This guide documents how the agents are wired, what context they receive, and how to evolve prompts and integrations. It is the source of truth for the AI layer used by tr(AI)ding.

## Agent System Overview
- Weekly (Sunday) agent: Performs macro/strategic “deep research” once per week. It writes a new dated section into `ai_weekly_research.md` and provides optional orders to rebalance for the coming week.
- Daily (weekday) agent: Runs after market close, evaluates portfolio state and decides whether to trade. The prompt is built in `app/prompts/prompts.py`.
- Scheduler: `app/schedule_runner.py` triggers `weekday_processing` or `sunday_processing` from `app/orchestrator.py` according to `WEEKDAY_AT` and `SUNDAY_AT` environment variables.

Both agents operate over portfolio data stored in SQLite (`db.sqlite3`). `app/data/collector.py` loads snapshots, while `app/data/inserter.py` upserts daily market candles into `stocks_info` and persists orders/positions/cash.

## Architecture At A Glance
- Orchestrator (`app/orchestrator.py`): Top-level flows for weekday/sunday runs. Assembles inputs, builds prompts, calls AI, applies results, and persists side effects.
- Prompts (`app/prompts/prompts.py`): Pure prompt builders returning strings. Keep all prompt wording centralized here.
- AI integration (`app/openai_integration.py`): Uses the OpenAI Agents SDK (`agents`) to run models.
  - Daily: `Agent` + `Runner.run_sync` returns a structured `AiDecision` (Pydantic).
  - Weekly: `Agent` with `WebSearchTool` + `Runner.run_streamed` for deep research; result is parsed into `WeeklyResearch`.
- Data access (`app/data/*.py`):
  - `db.py` bootstraps schema and provides a small query helper.
  - `collector.py` reads from SQLite and external sources (yfinance).
  - `inserter.py` performs all upserts and synchronization.
- Domain (`app/portfolio_manager.py`): In‑memory portfolio model and apply/compute helpers used after AI returns orders.

Guiding principles
- Separation of concerns: prompt text is isolated from IO; IO is isolated from domain updates.
- “Clean-ish” boundaries: Orchestrator composes modules; data access stays behind `collector/inserter`; domain mutations go through `portfolio_manager`.
- Deterministic core: business helpers avoid global state, easing testing and maintenance.

## Data Inputs Provided To Agents
Weekday (`app/orchestrator.py:55`):
- Positions dataframe: `app/data/collector.py:78` (`get_all_positions`) provides columns `date`, `ticker`, `qty`, `avg_price`.
- Latest cash dict: `app/data/collector.py:24` (`get_latest_cash`) → `{date, amount, total_portfolio_amount}`.
- Latest orders dataframe: `app/data/collector.py:98` (`get_latest_orders`) for the most recent trading date.
- Weekly research dict: `app/data/collector.py:128` (`get_latest_weekly_research`) pulls the latest dated section of `ai_weekly_research.md`.
- Market prices: `get_stock_data()` + `app/data/inserter.py:18` (`insert_latest_daily_data`) fetches daily OHLCV via yfinance and upserts into SQLite.

Sunday (`app/orchestrator.py:166`):
- Loads positions/cash/prices and last week’s orders, builds a weekend prompt via `Prompts.weekend_ai_prompt(...)`, runs `deep_research_async(...)`, and appends a new section to `ai_weekly_research.md`.

## Prompt Construction
Daily prompt: `Prompts.daily_ai_prompt(...)` includes
- Role & Objective: tactical portfolio manager aligned with Sunday theory.
- Daily Inputs: tickers, cash snapshot, latest orders preview, latest closing prices, and the last weekly research text.
- Constraints: no leverage/derivatives, ≤25% per position, ≥10% in cash, rebalance when needed.
- Response format: requires a daily summary, a decision (maintain vs. trades), and justification.

Weekend prompt: `Prompts.weekend_ai_prompt(...)` includes
- Role & Objective: produce a weekly macro thesis and any high‑level rebalancing orders.
- Inputs: same core tables plus the prior weekly research block for continuity.
- Response format: a strict JSON with keys `research` (string) and `orders` (list of `{ticker, qty, price}`), which we parse into `WeeklyResearch`.

Notes on prompt variables
- Ticker universe is deduped from positions.
- Cash totals may be `None`; keys still render to keep schema stable.
- Orders preview concatenates up to 3 latest orders.
- Embedded tables are plain‑text blocks from DataFrames (`to_string(index=False)`).

## Orchestration Flow
Weekday (`weekday_processing`)
1. Load inputs and write latest market candles to `stocks_info`.
2. Build daily prompt and call `send_prompt()` → `AiDecision` with fields:
   - `daily_summary: str`
   - `orders: list[Order{ticker, qty, price}]`
   - `explanation: str`
3. If orders exist, insert each into `orders`, update the in‑memory portfolio, sync `positions`, and write a cash snapshot using `compute_cash_after_orders`.

Sunday (`sunday_processing`)
1. Load inputs and write latest market candles.
2. Build weekend prompt and call `deep_research_async()` with `WebSearchTool` enabled.
3. Append the returned `research` text to `ai_weekly_research.md` under `# YYYY‑MM‑DD` and optionally enact suggested orders in future weekday runs.

## Configuration & Environment
Required
- `OPENAI_API_KEY` for both daily and weekly agents.

Optional (daily)
- `OPENAI_MODEL` (default: `gpt-4o-mini`).

Optional (weekly deep research)
- `OPENAI_RESEARCH_MODEL` (default: `o4-mini-deep-research-2025-06-26`).
- `OPENAI_BASE_URL`, `OPENAI_ORG`, `OPENAI_PROJECT` for routing.
- `OPENAI_TIMEOUT_SECONDS` (default: 120) and `OPENAI_MAX_RETRIES` (default: 2). Deep research overrides timeout to 1800s by default.

Database
- `DB_PATH` (default: `db.sqlite3`). Schema initialized by `app/data/db.py`.

Scheduling
- `WEEKDAY_AT` (HH:MM, default 18:00 local) and `SUNDAY_AT` (HH:MM, default 09:00).

## Conventions For Coding Agents (you)
- Keep changes minimal and scoped. Do not reformat unrelated files.
- Preserve public function signatures and Pydantic models (`AiDecision`, `WeeklyResearch`, `Order`).
- Prompt text belongs in `app/prompts/prompts.py`. Avoid scattering prompt strings elsewhere.
- Prefer pure helpers for transformations; keep side effects within orchestrator or `inserter`.
- SQLite writes should be idempotent and rely on primary keys/unique constraints already defined in `app/data/db.py`.
- When reading large files, chunk output (<=250 lines) and use `rg` for searches.
- If you add a new data input, reflect it in both: prompt builders and orchestrator wiring; update this file and `README.md`.
- Tests are light in this repo; validate by running weekday and sunday flows manually. If needed, use `deep_research_async(..., use_mock=True)` for offline testing.

## Extending Or Adding Agents
1. Create a new builder in `Prompts` with clear sections, constraints, and response expectations.
2. Update the orchestrator to call it and wire required data collectors.
3. Extend `collector.py`/`inserter.py` and the SQLite schema if you need more inputs; update `db.py` accordingly.
4. Document the response contract and update this guide and the README.
5. Keep `ai_weekly_research.md` concise to avoid prompt bloat.

## Maintaining Weekly Guidance
- Refresh `ai_weekly_research.md` each Sunday with a new dated header.
- Keep sections short (1–3 paragraphs) and directly actionable; the latest `YYYY‑MM‑DD` header is parsed and injected.
- Older sections are kept for history but ignored by default.

## Troubleshooting
- Missing API key: `send_prompt`/`deep_research_async` will raise; check `.env`.
- Empty datasets: Prompts still render, but agents may lack context; check SQLite tables and upstream collectors.
- Prompt too long: Consider summarizing tables before embedding or trimming to the top rows.
- Scheduler drift: Confirm server timezone and `WEEKDAY_AT`/`SUNDAY_AT`.

Language note: Prompt instructions are written in Portuguese (pt‑BR). Adjust text in `Prompts` if you need English output.
