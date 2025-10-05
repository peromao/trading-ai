import argparse
import json
import os
import re
from typing import Optional
from datetime import datetime

from agents import Agent, Runner, WebSearchTool
from agents.models import _openai_shared as _agents_openai_shared

from domain.models import AiDecision, Order, WeeklyResearch

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
    prompt: str,
    *,
    model: Optional[str] = None,
    use_mock: bool = False,
    mock_payload: Optional[str | dict] = None,
) -> WeeklyResearch:
    """Execute the weekly deep research workflow and return a structured result.

    Args:
        prompt: The user/system prompt to send.
        model: Optional model name. Defaults to `OPENAI_RESEARCH_MODEL`.
        use_mock: When True, bypass OpenAI and return a mock result.
        mock_payload: Optional JSON string or dict payload to use when `use_mock=True`.

    Env Vars:
        OPENAI_API_KEY (required unless `use_mock=True`)
        OPENAI_RESEARCH_MODEL (optional default model)
    """

    # Fast path: mocked response without contacting OpenAI
    if use_mock:
        try:
            if mock_payload is None:
                return _default_weekly_research_mock()
            if isinstance(mock_payload, str):
                payload = json.loads(mock_payload)
            else:
                payload = mock_payload
            return WeeklyResearch.model_validate(payload)
        except Exception:
            # Fallback to the baked-in mock if custom payload fails
            return _default_weekly_research_mock()

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
        print(f"\033[94m{datetime.now()} \033[0m {ev.type}")

    result = stream.final_output

    print(result)

    raw_text = result if isinstance(result, str) else str(result)
    return _parse_weekly_research(raw_text)


def _default_weekly_research_mock() -> WeeklyResearch:
    """Return a deterministic WeeklyResearch object for offline testing.

    The payload mirrors the structure produced by the real agent and uses
    the user-provided mock content to facilitate end-to-end testing without
    network access or API credentials.
    """
    payload = {
        "research": (
            "O cenário macro dos EUA segue favorável aos ativos de risco. Dados recentes de inflação vieram alinhados às expectativas, diminuindo o receio de que juros permaneçam mais altos por mais tempo ([www.reuters.com](https://www.reuters.com/business/wall-street-futures-mixed-investors-brace-inflation-data-2025-09-26/#:~:text=expectations%2C%20easing%20fears%20that%20persistent,week)). De fato, o Federal Reserve já iniciou cortes (0,25 ponto-base em 17/set, para faixa de 4,00–4,25%) e sinaliza mais reduções até o fim do ano ([www.reuters.com](https://www.reuters.com/business/fed-delivers-normal-sized-rate-cut-sees-steady-pace-further-reductions-miran-2025-09-17/#:~:text=On%20September%2017%2C%202025%2C%20the,growth%20and%20rising%20unemployment%2C%20while)). Projeções de mercado mostram praticamente 98% de chance de corte em outubro e 90% em dezembro ([www.reuters.com](https://www.reuters.com/business/bofa-global-research-moves-fed-rate-cut-forecast-october-december-2025-10-03/#:~:text=BofA%27s%20October%20cut%20projection,even%20without%20new%20employment%20data)), sustentadas por indicadores de desaquecimento do mercado de trabalho (em meio a paralisação do governo dos EUA que atrasou dados oficiais) ([www.reuters.com](https://www.reuters.com/business/bofa-global-research-moves-fed-rate-cut-forecast-october-december-2025-10-03/#:~:text=monetary%20policy,even%20without%20new%20employment%20data)). Assim, a política monetária está se tornando ainda mais expansionista, favorecendo ações de crescimento.\nNo campo do mercado de ações, os índices dos EUA vêm atingindo máximas históricas. Na última semana, S&P 500, Dow e Nasdaq bateram recordes, impulsionados principalmente por tecnologia e IA ([apnews.com](https://apnews.com/article/a08c07307c4483a3583fe2aaa1609637#:~:text=On%20Thursday%2C%20U,Investors)) ([apnews.com](https://apnews.com/article/be4301136953299b212c905e61e38fa9#:~:text=The%20S%26P%20500%20increased%20by,by%20OpenAI%27s%20new%20AI%20infrastructure)). Setores ligados a inteligência artificial continuam em alta (ex.: parcerias do OpenAI com empresas coreanas deram fôlego às ações de semicondutores e software ([apnews.com](https://apnews.com/article/be4301136953299b212c905e61e38fa9#:~:text=The%20S%26P%20500%20increased%20by,by%20OpenAI%27s%20new%20AI%20infrastructure)) ([apnews.com](https://apnews.com/article/a08c07307c4483a3583fe2aaa1609637#:~:text=largely%20ignored%20the%20shutdown%2C%20focusing,South%20Korean%20firms%2C%20boosting%20companies))). No entanto, há alertas de que uma bolha em ações de IA pode estar se formando devido ao excesso de euforia ([apnews.com](https://apnews.com/article/a08c07307c4483a3583fe2aaa1609637#:~:text=Concerns%20linger%20over%20a%20potential,its%20chemical%20unit%20to%20Berkshire)). Por outro lado, segmentos industriais e de infraestrutura (impulsionados por gastos públicos e reshoring) mantêm fundamentos sólidos no médio prazo, oferecendo diversificação defensiva e exposição ao crescimento econômico real.\nDiante desse contexto, adotamos uma postura mais ofensiva para a próxima semana, mas mantendo prudência com liquidez. Nossa exposição a tecnologia de ponta é reforçada: manteremos a posição em MSFT, líder em IA corporativa, e encerraremos o short em GOOG (cobertura de venda) porque a tendência geral do setor justifica reexecutar a compra de ações de alto crescimento. Paralelamente, diversificaremos adicionando posições em setores complementares. Em especial, entraremos em INTEL (INTC) e em um ETF de infraestrutura dos EUA (PAVE). A Intel recebeu recentemente um impulso significativo — a Nvidia anunciou investimento de US$5 bilhões na empresa ([www.reuters.com](https://www.reuters.com/world/asia-pacific/view-nvidias-5-billion-bet-intel-2025-09-18/#:~:text=Nvidia%20has%20announced%20a%20%245,while%20Nvidia%27s%20showed%20only)) — o que valida nossa tese de recuperação da fabricante de chips, ainda negociada a múltiplos bastante descontados. Já o ETF de infraestrutura captura o ciclo de investimentos domésticos (chegada de verbas de infraestrutura, CHIPS Act, etc.), oferecendo resiliência caso haja desaceleração econômica.\nApós os ajustes, cada posição representará cerca de 15–20% do portfólio, obedecendo ao limite máximo de 25% por ativo, e manteremos uma parcela em caixa acima de 10% como reserva. Minimizaremos alterações a não ser em resposta a novos dados (por exemplo, surpresas de inflação ou indicadores econômicos relevantes), evitando decisões precipitadas por ruído de mercado. Em resumo: seguimos otimistas com tecnologia e crescimento, mas equilibramos isso com diversificação em valor industrial e caixa para aproveitar oportunidades. Assim, para a próxima semana propomos cobrir o short em GOOG e comprar ações de GOOG, INTC e cotas de PAVE nas faixas de preço atuais."
        ),
        "orders": [
            {"ticker": "GOOG", "qty": 2, "price": 246.45},
            {"ticker": "INTC", "qty": 10, "price": 36.83},
            {"ticker": "PAVE", "qty": 10, "price": 45.00},
        ],
    }
    return WeeklyResearch.model_validate(payload)


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
