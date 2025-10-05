import argparse
import json
import os
import re
from typing import Optional

from agents import Agent, Runner, WebSearchTool
from agents.models import _openai_shared as _agents_openai_shared
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None

try:  # pragma: no cover - optional dependency
    import httpx
except Exception:  # pragma: no cover - optional dependency
    httpx = None

try:  # pragma: no cover - optional dependency
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - optional dependency
    AsyncOpenAI = None

if load_dotenv is not None:
    load_dotenv()  # nosec: loads .env into process env if present


class Order(BaseModel):
    ticker: str
    qty: int
    price: float = Field(..., ge=0.0)


class AiDecision(BaseModel):
    daily_summary: str
    orders: list[Order]
    explanation: str


class WeeklyResearch(BaseModel):
    research: str
    orders: list[Order]


DEFAULT_DAILY_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_RESEARCH_MODEL = os.getenv(
    "OPENAI_RESEARCH_MODEL", "o4-mini-deep-research-2025-06-26"
)
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_DEEP_TIMEOUT_SECONDS = 1800.0
JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def send_prompt(prompt: str, *, model: Optional[str] = None) -> AiDecision:
    """Send a prompt through a freshly created OpenAI Agent and return its reply.

    Args:
        prompt: The user prompt to send.
        model: Model name, defaults to env `OPENAI_MODEL` or `gpt-5-mini-2025-08-07`.

    Env Vars:
        OPENAI_API_KEY (required)
        OPENAI_MODEL (optional default model)
    """

    _ensure_api_key()

    model_name = model or DEFAULT_DAILY_MODEL
    _configure_openai_client(default_timeout_s=DEFAULT_TIMEOUT_SECONDS)

    agent = Agent(name="Assistant", model=model_name, output_type=AiDecision)

    result = Runner.run_sync(agent, prompt)
    return result.final_output


async def deep_research_async(
    prompt: str, *, model: Optional[str] = None
) -> WeeklyResearch:
    """Send a prompt through a freshly created OpenAI Agent and return its reply.

    Args:
        prompt: The user prompt to send.
        model: Model name, defaults to env `OPENAI_MODEL` or `gpt-5-mini-2025-08-07`.

    Env Vars:
        OPENAI_API_KEY (required)
        OPENAI_MODEL (optional default model)
    """

    _ensure_api_key()

    model_name = model or DEFAULT_RESEARCH_MODEL
    _configure_openai_client(default_timeout_s=DEFAULT_DEEP_TIMEOUT_SECONDS)

    instructions = (
        "Conduza um deep research completo, fundamentado e acionável sobre o contexto fornecido. "
        "Use a ferramenta de busca quando necessário para verificar fatos e enriquecer a análise. "
        "Não faça perguntas ao usuário; formule hipóteses e valide-as. "
        "Sua saída deve ser estruturada e diretamente aplicável à carteira. "
        "Retorne um JSON estrito com o seguinte formato sem cercas de código: "
        '{"research": string, "orders": [{"ticker": string, "qty": integer, "price": number}]}. '
        'Se não houver ordens, use uma lista vazia em "orders".'
    )

    agent = Agent(
        name="Assistant",
        model=model_name,
        tools=[WebSearchTool()],
        instructions=instructions,
    )

    stream = Runner.run_streamed(agent, prompt)

    async for ev in stream.stream_events():
        if getattr(ev, "type", None) == "run_item_stream_event":
            if getattr(ev, "name", None) == "tool_called":
                item = getattr(ev, "item", None)
                raw = getattr(item, "raw_item", None)
                if raw is not None and getattr(raw, "type", None) == "web_search_call":
                    action = getattr(raw, "action", None)
                    atype = getattr(action, "type", None)
                    if atype == "search":
                        print(f"[Web search] query={getattr(action, 'query', None)!r}")
                    elif atype == "open_page":
                        print(f"[Open page] url={getattr(action, 'url', None)}")
                    elif atype == "find":
                        print(
                            f"[Find] pattern={getattr(action, 'pattern', None)!r} in url={getattr(action, 'url', None)}"
                        )

    result = stream.final_output

    raw_text = result if isinstance(result, str) else str(result)
    return _parse_weekly_research(raw_text)


def _ensure_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY environment variable")
    return api_key


def _configure_openai_client(*, default_timeout_s: float) -> None:
    """Configure a shared OpenAI Async client with an increased timeout.

    The Agents SDK will reuse this client via its OpenAIProvider if set.
    """
    try:
        # Reuse if already set
        existing = _agents_openai_shared.get_default_openai_client()
        if existing is not None:
            return

        timeout_override = os.getenv("OPENAI_TIMEOUT_SECONDS")
        timeout_val = (
            float(timeout_override) if timeout_override else float(default_timeout_s)
        )
        max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))

        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or None
        organization = os.getenv("OPENAI_ORG") or None
        project = os.getenv("OPENAI_PROJECT") or None

        http_client = None
        if httpx is not None:
            http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    timeout_val, connect=30.0, read=timeout_val, write=timeout_val
                )
            )

        if AsyncOpenAI is not None:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                organization=organization,
                project=project,
                http_client=http_client,
                timeout=timeout_val,
                max_retries=max_retries,
            )
            _agents_openai_shared.set_default_openai_client(client)
    except Exception:
        # If anything fails here, we fall back to SDK defaults
        return


def _parse_weekly_research(raw_text: str) -> WeeklyResearch:
    text = (raw_text or "").strip()
    if not text:
        return WeeklyResearch(research="", orders=[])

    for candidate in (text, _extract_json_block(text)):
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
            return WeeklyResearch.model_validate(payload)
        except Exception:
            continue

    return WeeklyResearch(research=text, orders=[])


def _extract_json_block(text: str) -> str | None:
    match = JSON_FENCE_PATTERN.search(text)
    return match.group(1) if match else None


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Send a prompt via OpenAI Agents SDK")
    parser.add_argument("prompt", nargs="+", help="Prompt to send")
    parser.add_argument("--system", dest="system", help="Optional system instruction")
    parser.add_argument("--model", dest="model", help="Model to use (default from env)")
    args = parser.parse_args(argv)

    prompt = " ".join(args.prompt)
    text = send_prompt(prompt, model=args.model)
    print(text)


if __name__ == "__main__":  # pragma: no cover
    main()
