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

**Data inputs**
- `data/positions.csv` (portfolio positions)
  - Columns: `date,ticker,qty,avg_price`
  - Tickers are cleaned of quotes/whitespace.
  - The orchestrator derives the tickers universe from all rows (not only latest date).
- `data/cash.csv` (cash snapshot)
  - Columns: `date, amount, total_portfolio_amount` (header spacing is normalized)
- `data/orders.csv` (executed orders)
  - Columns: `date, ticker, qty, price`
  - The app reads ALL rows from the latest `date` present.
- `ai_weekly_research.md` (weekly strategy)
  - Markdown with dated headers like `# YYYY-MM-DD`. The most recent dated section is parsed and used as strategic guidance.

**Run the orchestrator (weekday)**
- Populate the CSVs and `.env` as above.
- Run once:
  - `python app/orchestrator.py --run weekday`
  - or: `python -m app.orchestrator --run weekday`
  - Behavior:
    - Loads positions and derives unique tickers.
    - Fetches latest daily prices with yfinance and updates `data/stocks_info.csv`.
    - Loads latest cash, latest-date orders, and the latest weekly research section.
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
- `app/data/collector.py`
  - `get_all_positions()`: loads and cleans positions.
  - `get_latest_cash()`: reads the latest cash row.
  - `get_latest_orders()`: returns all rows from the latest date in `orders.csv`.
  - `get_latest_weekly_research()`: parses the latest dated section from the weekly research Markdown.
- `app/data/inserter.py`: persists the latest daily market row per ticker to `data/stocks_info.csv`.
- `app/prompts/prompts.py`: `Prompts.daily_ai_prompt(...)` builds the daily prompt including CSV snapshots and research.
- `app/openai_integration.py`: minimal wrapper over the OpenAI Agents SDK `responses.create(...)` API.
- `app/orchestrator.py`: coordinates the weekday/sunday flows and calls the AI.
