import os
import argparse
from typing import Optional

# Load env vars from .env automatically (repo root or parents)
try:
    from dotenv import load_dotenv
    load_dotenv()  # nosec: loads .env into process env if present
except Exception:
    # If python-dotenv isn't installed, fall back to existing environment
    pass

try:
    # OpenAI Python SDK (aka Agents SDK)
    from openai import OpenAI  # type: ignore
except Exception as exc:  # pragma: no cover
    OpenAI = None  # type: ignore
    _import_error = exc
else:
    _import_error = None


def send_prompt(prompt: str, *, system: Optional[str] = None, model: Optional[str] = None) -> str:
    """Send a prompt and return the model's response using OpenAI Agents SDK.

    Args:
        prompt: The user prompt to send.
        system: Optional system instruction to guide behavior.
        model: Model name, defaults to env `OPENAI_MODEL` or `gpt-4o-mini`.

    Env Vars:
        OPENAI_API_KEY (required)
        OPENAI_BASE_URL (optional, for self-hosted gateways)
        OPENAI_MODEL (optional default model)
    """
    if OpenAI is None:  # pragma: no cover
        raise RuntimeError(
            f"openai SDK is not installed: {_import_error}. Install with `pip install openai`."
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY environment variable")

    base_url = os.getenv("OPENAI_BASE_URL")
    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Initialize client; allow custom base_url if provided
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    # Use the Responses API (Agents SDK) for a simple single-shot prompt
    # Prefer `instructions` for system guidance when provided.
    resp = client.responses.create(
        model=model,
        input=prompt,
        instructions=system or None,
    )

    # Robustly extract text output across SDK versions
    text = getattr(resp, "output_text", None)
    if isinstance(text, str) and text:
        return text

    # Fallback parse for older/newer response shapes
    try:
        # Newer SDK: resp.output is a list of blocks with content
        outputs = getattr(resp, "output", None) or []
        if outputs:
            contents = outputs[0].get("content") if isinstance(outputs[0], dict) else getattr(outputs[0], "content", [])
            if contents:
                first = contents[0]
                if isinstance(first, dict):
                    return first.get("text", {}).get("value") or ""
                # object-like with attributes
                if hasattr(first, "text") and hasattr(first.text, "value"):
                    return first.text.value or ""
    except Exception:
        pass

    # Last resort: string repr
    return str(resp)


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
