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

**Run the code**
- Example (directly executing a module or script):
  - `python app/data/collector.py`
  - or, if structured as a module: `python -m app.data.collector`

When you’re done, deactivate the virtual environment:
- `deactivate`
