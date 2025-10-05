from __future__ import annotations

from typing import Dict, Any, List, Optional


def _df_to_text(df) -> str:
    """Render a DataFrame-like object as a plain-text table."""
    if df is None or getattr(df, "empty", True):
        return ""
    try:
        return df.to_string(index=False)
    except Exception:
        return ""


class Prompts:
    """Centralized prompt builder for AI requests.

    Add new prompt builders here and import this class where needed.
    """

    @staticmethod
    def daily_ai_prompt(
        *,
        positions_df,  # pandas.DataFrame
        latest_cash: Dict[str, Any],
        latest_orders,  # pandas.DataFrame | None
        weekly_research: Dict[str, Any],
        latest_prices_df=None,  # pandas.DataFrame | None
    ) -> str:
        """Build a concise daily AI prompt using portfolio and research context.

        Expects cleaned dataframes/objects from collector helpers.
        """
        # Positions summary
        tickers: List[str] = []
        if positions_df is not None and not positions_df.empty:
            seen = set()
            for t in positions_df.get("ticker", []).astype(str).tolist():
                if t and t not in seen:
                    seen.add(t)
                    tickers.append(t)
        tickers_str = ", ".join(tickers) if tickers else "(none)"

        # Cash summary
        cash_amt = latest_cash.get("amount") if latest_cash else None
        total_amt = latest_cash.get("total_portfolio_amount") if latest_cash else None

        # Latest orders summary
        orders_rows = 0
        orders_preview: str = ""
        if latest_orders is not None and getattr(latest_orders, "empty", True) is False:
            orders_rows = len(latest_orders)
            try:
                subset = latest_orders.head(3)
                orders_preview = "; ".join(
                    f"{str(r.get('date'))[:10]} {r.get('ticker')} x{r.get('qty')} @ {r.get('price')}"
                    for _, r in subset.iterrows()
                )
            except Exception:
                orders_preview = ""
        orders_block = _df_to_text(latest_orders) or "[sem ordens recentes]"

        # Weekly research (full text)
        research_date = (weekly_research or {}).get("date_str", "")
        research_text = (weekly_research or {}).get("text", "").strip()

        # Positions snapshot
        positions_block = _df_to_text(positions_df) or "[sem posições registradas]"

        # Latest market prices (daily close)
        try:
            have_prices = (
                latest_prices_df is not None
                and getattr(latest_prices_df, "empty", True) is False
            )
        except Exception:
            have_prices = False
        price_rows = 0
        prices_block = "[sem preços disponíveis]"
        if have_prices:
            price_rows = len(latest_prices_df)
            prices_block = _df_to_text(latest_prices_df) or "[sem preços disponíveis]"

        prompt = (
            "Você é um gestor tático de uma carteira de ações dos EUA.\n"
            "Seu papel é analisar diariamente os dados recebidos sobre a carteira atual, execuções passadas e caixa disponível, e decidir se deve comprar, vender ou manter ativos, alinhado à teoria macro definida no domingo.\n\n"
            "Objetivo\n\n"
            "- Maximizar o retorno acumulado em 5 anos.\n"
            "- Seguir a estratégia macro definida no domingo.\n"
            "- Proteger a carteira de riscos excessivos e perdas permanentes.\n"
            "- Agir apenas quando necessário (evitar trades desnecessários).\n\n"
            "Insumos recebidos hoje (dados reais)\n\n"
            f"- Universo de tickers nas posições: {tickers_str}\n"
            f"- Caixa: amount={cash_amt}, total_portfolio_amount={total_amt}\n"
            f"- Ordens mais recentes (linhas: {orders_rows}; prévia: {orders_preview})\n"
            f"- Dados de preços de fechamento de hoje (linhas: {price_rows}) listados em latest_prices\n"
            "\n--- positions snapshot ---\n"
            f"{positions_block}\n"
            "--- latest_prices (fechamento oficial do dia) ---\n"
            f"{prices_block}\n"
            "--- latest_orders (última data) ---\n"
            f"{orders_block}\n"
            f"--- weekly_research ({research_date}) ---\n"
            f"{research_text}\n\n"
            "Restrições (sempre respeitar)\n\n"
            "- Sem alavancagem.\n"
            "- Sem derivativos.\n"
            "- Considerar custos de transação simbólicos a cada trade.\n"
            "- Não concentrar >25% do portfólio em um único ativo.\n"
            "- Manter pelo menos 10% do portfólio em caixa.\n"
            "- Rebalancear quando necessário.\n"
            "- Não é obrigatório agir todos os dias.\n\n"
            "Como responder\n\n"
            "- Resumo diário (1–2 parágrafos): análise do dia, impacto dos preços nas posições, riscos e aderência à teoria macro.\n"
            "- Decisão tática: Manter (sem novas ordens) OU Comprar/Vender (listar ordens com ticker, quantidade, preço-alvo aproximado).\n"
            "- Justificativa: por que essas ordens ou inação fazem sentido, considerando teoria macro e restrições.\n\n"
            "Importante\n\n"
            "- Se não houver oportunidades claras, afirme: 'Hoje não há trades recomendados.'\n"
            "- Se houver necessidade de ajuste (ex.: concentração alta, caixa abaixo do limite, posição desalinhada da macro), proponha rebalanceamento.\n"
            "- Você é o agente tático; siga o plano estratégico de domingo como guia.\n"
            "- Sempre referenciar a coluna close de latest_prices para justificar preços de entrada/saída.\n"
        )
        return prompt

    @staticmethod
    def weekend_ai_prompt(
        *,
        positions_df,  # pandas.DataFrame
        latest_cash: Dict[str, Any],
        weekly_orders,  # pandas.DataFrame | None
        weekly_research: Dict[str, Any],
        latest_prices_df=None,  # pandas.DataFrame | None,
    ) -> str:
        """Build the weekend prompt using portfolio and research context.

        Expects cleaned dataframes/objects from collector helpers.
        """
        # Positions summary
        tickers: List[str] = []
        if positions_df is not None and not positions_df.empty:
            seen = set()
            for t in positions_df.get("ticker", []).astype(str).tolist():
                if t and t not in seen:
                    seen.add(t)
                    tickers.append(t)
        tickers_str = ", ".join(tickers) if tickers else "(none)"

        # Cash summary
        cash_amt = latest_cash.get("amount") if latest_cash else None
        total_amt = latest_cash.get("total_portfolio_amount") if latest_cash else None

        # Latest orders summary
        orders_rows = 0
        orders_preview: str = ""
        if weekly_orders is not None and getattr(weekly_orders, "empty", True) is False:
            orders_rows = len(weekly_orders)
            try:
                subset = weekly_orders.head(3)
                orders_preview = "; ".join(
                    f"{str(r.get('date'))[:10]} {r.get('ticker')} x{r.get('qty')} @ {r.get('price')}"
                    for _, r in subset.iterrows()
                )
            except Exception:
                orders_preview = ""
        orders_block = _df_to_text(weekly_orders) or "[sem ordens recentes]"

        # Weekly research (full text)
        last_research_date = (weekly_research or {}).get("date_str", "")
        last_research_text = (weekly_research or {}).get("text", "").strip()

        # Positions snapshot
        positions_block = _df_to_text(positions_df) or "[sem posições registradas]"

        # Latest market prices (daily close)
        try:
            have_prices = (
                latest_prices_df is not None
                and getattr(latest_prices_df, "empty", True) is False
            )
        except Exception:
            have_prices = False
        price_rows = 0
        prices_block = "[sem preços disponíveis]"
        if have_prices:
            price_rows = len(latest_prices_df)
            prices_block = _df_to_text(latest_prices_df) or "[sem preços disponíveis]"

        prompt = (
            "Você é um gestor estratégico de uma carteira de ações dos EUA.\n"
            "Seu papel é criar uma teoria macro para ser seguida durante a semana, baseado nos dados recebidos sobre a carteira atual, execuções passadas, caixa disponível e acontecimentos da última semana no mundo, e decidir quais ações manter, vender ou comprar \n\n"
            "Objetivo\n\n"
            "- Maximizar o retorno acumulado em 5 anos.\n"
            "- Criar uma estratégia macro para ser seguida na próxima semana.\n"
            "- Escolher como e se mudar a carteira atual\n"
            "- Analisar se houve mudanças consideráveis da última teoria e se é necessário mudar algo na carteira ou teoria.\n\n"
            "Insumos recebidos hoje (dados reais)\n\n"
            f"- Universo de tickers nas posições: {tickers_str}\n"
            f"- Caixa: amount={cash_amt}, total_portfolio_amount={total_amt}\n"
            f"- Ordens da semana (linhas: {orders_rows}; prévia: {orders_preview})\n"
            f"- Dados de preços de fechamento de hoje (linhas: {price_rows}) listados em latest_prices\n"
            "\n--- positions snapshot ---\n"
            f"{positions_block}\n"
            "--- latest_prices (fechamento oficial do dia) ---\n"
            f"{prices_block}\n"
            "--- latest_orders (última data) ---\n"
            f"{orders_block}\n"
            f"--- weekly_research ({last_research_date}) ---\n"
            f"{last_research_text}\n\n"
            "Restrições (sempre respeitar)\n\n"
            "- Sem alavancagem.\n"
            "- Sem derivativos.\n"
            "- Considerar custos de transação simbólicos a cada trade.\n"
            "- Não concentrar >25% do portfólio em um único ativo.\n"
            "- Manter pelo menos 10% do portfólio em caixa.\n"
            "- Rebalancear quando necessário.\n"
            "- Não é obrigatório agir todos os dias.\n\n"
            "Como responder\n\n"
            "- research: Criação da teoria macro para a próxima semana\n"
            "- orders: Manter (sem novas ordens) OU Comprar/Vender (listar ordens com ticker, quantidade, preço-alvo aproximado).\n"
            "Importante\n\n"
            "- Se não houver oportunidades claras, afirme: 'Hoje não há trades recomendados.'\n"
            "- Se houver necessidade de ajuste (ex.: concentração alta, caixa abaixo do limite, posição desalinhada da macro), proponha rebalanceamento.\n"
            "- Sempre referenciar a coluna close de latest_prices para justificar preços de entrada/saída.\n"
        )
        return prompt

    @staticmethod
    def quick_test_prompt() -> str:
        """Simple fallback/test prompt."""
        return "Say hello and confirm you received the context."
