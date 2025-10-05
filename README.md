# tr(AI)ding

Automated portfolio manager for U.S. equities powered by two cooperating AI agents:
- Weekly agent (Sunday) performs macro “deep research” and writes the week’s strategy.
- Daily agent (Monday–Friday) executes tactical decisions aligned to that strategy.

The system orchestrates data collection (positions, cash, executed orders), updates market prices (yfinance), builds prompts, and runs OpenAI models via the Agents SDK. It targets a medium/long‑term portfolio with risk controls and minimal churn, while remaining responsive day to day.

Language note: The prompt instructions are in Portuguese (pt‑BR). Change `app/prompts/prompts.py` if you prefer English.

## Features
- Two agents with clear roles: strategic (weekly) and tactical (daily)
- SQLite persistence for cash, positions, orders, and market candles
- YFinance daily OHLCV ingestion with idempotent upserts
- OpenAI Agents SDK integration with optional web search for weekly research
- Simple scheduler with configurable run times

## Architecture
- Orchestrator (`app/orchestrator.py`)
  - Weekday flow: assembles inputs, builds prompt (`Prompts.daily_ai_prompt`), calls `send_prompt`, applies orders to the portfolio, syncs positions/cash.
  - Sunday flow: assembles inputs, builds weekend prompt, runs `deep_research_async` with `WebSearchTool`, appends a new dated section to `ai_weekly_research.md`.
- Prompts (`app/prompts/prompts.py`)
  - Centralized builders for weekday/weekend prompts; tables are embedded as plain‑text for model readability.
- AI Integration (`app/openai_integration.py`)
  - Daily: `Agent` + `Runner.run_sync(...)` returns `AiDecision` with `daily_summary`, `orders`, `explanation`.
  - Weekly: `Agent(tools=[WebSearchTool()])` + `Runner.run_streamed(...)` returns `WeeklyResearch` with `research` and optional `orders`.
  - Uses a shared `AsyncOpenAI` client (if available) with configurable timeouts/retries.
- Data Access (`app/data/*.py`)
  - `db.py`: schema bootstrap and helpers.
  - `collector.py`: reads SQLite and external sources (yfinance) and cleans tickers.
  - `inserter.py`: upserts market data; inserts orders; syncs positions; writes cash snapshots.
- Domain (`app/portfolio_manager.py`)
  - Minimal portfolio model; order application and cash arithmetic.
- Domain Models (`app/domain/models.py`)
  - Pydantic models shared across the app: `Order`, `AiDecision`, `WeeklyResearch`.

Design style: “clean‑ish” layering
- Prompt wording is isolated from IO; IO is isolated from domain mutations.
- Functions return simple dataclasses/Pydantic models to keep boundaries explicit.

## Data Model
SQLite (default `db.sqlite3`, configurable via `DB_PATH`):
- `cash(date PRIMARY KEY, amount REAL, total_portfolio_amount REAL)`
- `positions(date TEXT NOT NULL, ticker TEXT NOT NULL, qty REAL, avg_price REAL, UNIQUE(date,ticker))`
- `orders(id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, ticker TEXT NOT NULL, qty REAL, price REAL)`
- `stocks_info(date TEXT NOT NULL, ticker TEXT NOT NULL, open REAL, high REAL, low REAL, close REAL, volume INTEGER, dividends REAL DEFAULT 0.0, stock_splits REAL DEFAULT 0.0, PRIMARY KEY(date,ticker))`

`ai_weekly_research.md` stores weekly strategy sections with headers like `# YYYY-MM-DD`. The most recent dated section is parsed and injected into prompts.

## Quickstart
Prerequisites
- Python 3.9+

Environment
1) Create and activate a virtual environment
- macOS/Linux
  - `python3 -m venv .venv`
  - `source .venv/bin/activate`
- Windows (PowerShell)
  - `python -m venv .venv`
  - `.venv\Scripts\Activate.ps1`

2) Upgrade pip and install dependencies
- `python -m pip install --upgrade pip`
- `pip install -r requirements.txt`
- Agents SDK and OpenAI client (if not present):
  - `pip install agents openai`

3) Configure `.env` (auto‑loaded via `python-dotenv`)
- Required: `OPENAI_API_KEY=...`
- Optional (daily): `OPENAI_MODEL=gpt-4o-mini`
- Optional (weekly): `OPENAI_RESEARCH_MODEL=o4-mini-deep-research-2025-06-26`
- Optional routing: `OPENAI_BASE_URL`, `OPENAI_ORG`, `OPENAI_PROJECT`
- Optional timeouts/retries: `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_RETRIES`
- Optional DB path: `DB_PATH`

Example `.env`
```
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4o-mini
# OPENAI_RESEARCH_MODEL=o4-mini-deep-research-2025-06-26
# OPENAI_BASE_URL=https://your-gateway/v1
# DB_PATH=/abs/path/to/db.sqlite3
```

## Running
Weekday run
- `python app/orchestrator.py --run weekday`
- or `python -m app.orchestrator --run weekday`
Behavior
- Loads positions, dedupes tickers, fetches latest daily candles via yfinance, upserts into `stocks_info`.
- Loads latest cash, latest‑date orders, and latest weekly research.
- Builds the daily prompt and calls the model. If orders are returned, inserts them, updates positions, and writes a new cash snapshot.

Sunday run
- `python app/orchestrator.py --run sunday`
Behavior
- Loads positions/cash/prices and last week’s orders.
- Builds the weekend prompt and launches deep research with web search tool.
- Appends a new dated section to `ai_weekly_research.md`.

Scheduler
- Configure local times: `WEEKDAY_AT` (default 18:00), `SUNDAY_AT` (default 09:00)
- Start loop: `python -m app.schedule_runner`
- Run immediately and continue scheduling:
  - `python -m app.schedule_runner --run-now weekday`
  - `python -m app.schedule_runner --run-now sunday`

## Development
Project layout highlights
- `app/data/db.py`: connection + schema bootstrap
- `app/data/collector.py`: readers for cash/positions/orders/weekly_research and yfinance wrapper
- `app/data/inserter.py`: idempotent upserts for market data and syncing routines
- `app/prompts/prompts.py`: central prompt builders (weekday + weekend)
- `app/openai_integration.py`: Agents SDK glue; daily and weekly runners
- `app/orchestrator.py`: end‑to‑end flows
- `app/portfolio_manager.py`: domain helpers to apply orders and compute cash
- `app/domain/models.py`: Pydantic models `Order`, `AiDecision`, `WeeklyResearch`

Style & conventions
- Keep prompt text centralized in `Prompts`. Avoid duplicating strings elsewhere.
- Keep data transforms pure; isolate side effects in orchestrator/inserters.
- Maintain the Pydantic contracts:
  - `AiDecision { daily_summary:str, orders:list[Order], explanation:str }`
  - `Order { ticker:str, qty:int, price:float>=0 }`
  - `WeeklyResearch { research:str, orders:list[Order] }`
 - Import models from `app.domain.models` (or via re-export `app.domain`). Example:
   - `from app.domain.models import Order, AiDecision, WeeklyResearch`

Seeding the database (example)
```sql
-- Using sqlite3 CLI
-- Create tables automatically by running any flow once, or manually:
--   python -m app.orchestrator --run weekday
-- Then seed initial data if needed:
INSERT INTO cash(date, amount, total_portfolio_amount) VALUES ('2025-01-01', 10000, NULL)
  ON CONFLICT(date) DO UPDATE SET amount=excluded.amount;
INSERT INTO positions(date, ticker, qty, avg_price) VALUES ('2025-01-01','AAPL',10,180.0);
```

Offline testing for weekly research
```python
from app.openai_integration import deep_research_async
import asyncio

async def demo():
    res = await deep_research_async("test context", use_mock=True)
    print(res.model_dump())

asyncio.run(demo())
```

## Troubleshooting
- Missing API key: ensure `OPENAI_API_KEY` is present in `.env`.
- Empty prompts: verify that positions/cash/orders tables have data.
- Long prompts: reduce embedded table rows or trim `ai_weekly_research.md`.
- Scheduler timing: confirm server timezone; adjust `WEEKDAY_AT`/`SUNDAY_AT`.
- Dependencies: if you see `ModuleNotFoundError: agents` or `openai`, install them with `pip install agents openai` and consider adding them to `requirements.txt`.

## Disclaimer
This project is for research/education. It is not financial advice. Use at your own risk.
