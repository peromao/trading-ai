# tr(AI)ding

tr(AI)ding is an experimental system for automating a U.S. equities investment portfolio using AI agents.
It combines two complementary agents:

Weekly agent (Sunday): performs macro/strategic analysis of the portfolio and produces a “market theory” to guide the upcoming week.

Daily agent (Monday–Friday): runs after market close and makes tactical decisions (buy, sell, hold, rebalance, or take no action), always aligned with the weekly strategy.

The project orchestrates portfolio data collection (positions, cash, executed orders), updates market prices, builds prompts, and executes interactions with OpenAI models. The goal is to simulate a medium/long-term portfolio with diversification and risk management rules, while still allowing dynamic day-to-day adjustments.

## QuickStart

Quickstart instructions to set up a virtual environment, install dependencies, and run the code.

**Prerequisites**
- Python 3.9+ installed (`python3 --version`)

**Create and activate a virtual environment**
- macOS/Linux:
  - `python3 -m venv .venv`
  - `source .venv/bin/activate`
- Windows (PowerShell):
  - `python -m venv .venv`
  - `.venv\\Scripts\\Activate.ps1`

Upgrade `pip` (recommended)
- `python -m pip install --upgrade pip`

**Install dependencies**
- `pip install -r requirements.txt`

OpenAI integration (Agents SDK)
- The app uses the OpenAI Python SDK (aka Agents SDK) via `app/openai_integration.py`.
- Environment variables are loaded automatically from `.env` using `python-dotenv`.
- Required variables in `.env` (repo root):
  - `OPENAI_API_KEY=...` (required)
  - `OPENAI_MODEL=gpt-4o-mini` (optional; defaults to `gpt-4o-mini`)
  - `OPENAI_BASE_URL=...` (optional; for gateways/proxies)

Example `.env`:
```
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4o-mini
# OPENAI_BASE_URL=https://your-gateway/v1
```

If you need additional libraries, add them with `pip install <package>` and then freeze the current set into `requirements.txt` so others can reproduce your environment:
- `pip freeze > requirements.txt`

**Data storage**
- Local SQLite database at `db.sqlite3` (configurable with env `DB_PATH`).
  - Tables and keys:
    - `cash(date PRIMARY KEY, amount, total_portfolio_amount)`
    - `positions(date, ticker, qty, avg_price, UNIQUE(date, ticker))`
    - `orders(id INTEGER PRIMARY KEY AUTOINCREMENT, date, ticker, qty, price)`
    - `stocks_info(date, ticker, open, high, low, close, volume, dividends, stock_splits, PRIMARY KEY(date, ticker))`
- `ai_weekly_research.md` (weekly strategy)
  - Markdown with dated headers like `# YYYY-MM-DD`. The most recent dated section is parsed and used as strategic guidance.

**Run the orchestrator (weekday)**
- Ensure the SQLite tables contain your starting data and `.env` is configured.
- Run once:
  - `python app/orchestrator.py --run weekday`
  - or: `python -m app.orchestrator --run weekday`
  - Behavior:
    - Loads positions from SQLite and derives unique tickers.
    - Fetches latest daily prices with yfinance and upserts into SQLite table `stocks_info`.
    - Loads latest cash and latest-date orders from SQLite, and the latest weekly research section.
    - Builds a compact prompt with this data (`app/prompts/prompts.py`) and sends it to the OpenAI model.

**Run the Sunday processing (optional)**
- `python app/orchestrator.py --run sunday`
- Collects data similarly but does not send the AI prompt by default.

**Start the recurring scheduler**
- Configure times (local timezone):
  - `WEEKDAY_AT` in `HH:MM` (default: `18:00`)
  - `SUNDAY_AT` in `HH:MM` (default: `09:00`)
- Start the loop:
  - `python -m app.schedule_runner`
- Optionally kick off a job immediately and continue scheduling:
  - `python -m app.schedule_runner --run-now weekday`
  - `python -m app.schedule_runner --run-now sunday`

When you’re done, deactivate the virtual environment:
- `deactivate`

Project structure highlights
- `app/data/db.py`: SQLite helpers (connection, schema init, query helper).
- `app/data/collector.py`
  - `get_all_positions()`: loads and cleans positions (from SQLite).
  - `get_latest_cash()`: reads the latest cash row (from SQLite).
  - `get_latest_orders()`: returns all rows from the latest date in SQLite `orders`.
  - `get_latest_weekly_research()`: parses the latest dated section from the weekly research Markdown.
- `app/data/inserter.py`: upserts the latest daily market row per ticker into SQLite `stocks_info`.
- `app/prompts/prompts.py`: `Prompts.daily_ai_prompt(...)` builds the daily prompt (includes plain-text table snapshots derived from DataFrames for readability).
- `app/openai_integration.py`: minimal wrapper over the OpenAI Agents SDK `responses.create(...)` API.
- `app/orchestrator.py`: coordinates the weekday/sunday flows and calls the AI.
