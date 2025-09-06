# trading-ai

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

If you need additional libraries, add them with `pip install <package>` and then freeze the current set into `requirements.txt` so others can reproduce your environment:
- `pip freeze > requirements.txt`

**Run the orchestrator (weekday test)**
- Set optional environment variables:
  - `TICKERS` (comma-separated, default: `AAPL,MSFT,GOOGL`)
- Run the weekday processing once:
  - `python app/orchestrator.py --run weekday`
  - or as a module: `python -m app.orchestrator --run weekday`

**Run the Sunday processing (optional)**
- Set optional `SUNDAY_TICKERS` (falls back to `TICKERS`).
- Run once:
  - `python app/orchestrator.py --run sunday`

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
