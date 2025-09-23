import os
import argparse
from typing import Optional
from agents import Agent, Runner
from pydantic import BaseModel

# Load env vars from .env automatically (repo root or parents)
try:
    from dotenv import load_dotenv

    load_dotenv()  # nosec: loads .env into process env if present
except Exception:
    # If python-dotenv isn't installed, fall back to existing environment
    pass


class Order(BaseModel):
    ticker: str
    qty: int


class AiDecision(BaseModel):
    daily_summary: str
    orders: list[Order]
    explanation: str


def send_prompt(prompt: str, *, model: Optional[str] = None) -> AiDecision:
    """Send a prompt through a freshly created OpenAI Agent and return its reply.

    Args:
        prompt: The user prompt to send.
        model: Model name, defaults to env `OPENAI_MODEL` or `gpt-5-mini-2025-08-07`.

    Env Vars:
        OPENAI_API_KEY (required)
        OPENAI_MODEL (optional default model)
    """

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY environment variable")

    model = model or os.getenv("OPENAI_MODEL", "gpt-5-mini-2025-08-07")

    agent = Agent(name="Assistant", output_type=AiDecision)

    result = Runner.run_sync(agent, prompt)
    return result.final_output


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send a prompt via OpenAI Agents SDK")
    parser.add_argument("prompt", nargs="+", help="Prompt to send")
    parser.add_argument("--system", dest="system", help="Optional system instruction")
    parser.add_argument("--model", dest="model", help="Model to use (default from env)")
    args = parser.parse_args(argv)

    prompt = " ".join(args.prompt)
    text = send_prompt(prompt, system=args.system, model=args.model)
    print(text)


if __name__ == "__main__":  # pragma: no cover
    main()
