"""
tests/test_deal_node.py — Unit tests for agents/nodes/deal_node.py (Inc 4).

Cobre o gatilho OR (target_price / threshold histórico), a aritmética de
savings_pct/discount_pct, o tie-break por STORE_DISPLAY_NAMES, os edge cases
(sem validados, sem baseline) e o resumo (LLM mockado / template fallback).
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from agents.nodes.deal_node import DealNode


# --- helpers -------------------------------------------------------------------

def _validated(store_id: str, price: float, **overrides) -> dict:
    """Shape exato do output do AnalystNode (Inc 3)."""
    v = {
        "store_id": store_id,
        "price": price,
        "available": True,
        "url": f"https://{store_id}.com/produto",
        "stock_label": "Em estoque",
        "reason": "ok",
        "history_avg": 1000.0,
        "history_min": 900.0,
        "history_n": 5,
        "valid": True,
        "flagged_suspicious": False,
    }
    v.update(overrides)
    return v


def _state(validated, target_price=None, analysis=None, errors=None, product="RTX 4060") -> dict:
    return {
        "product": product,
        "search_term": "rtx-4060",
        "target_price": target_price,
        "iteration": 1,
        "validated": validated,
        "suspicious": [],
        "analysis": analysis or {},
        "errors": errors or [],
        "trace": [],
    }


# --- gatilho OR ----------------------------------------------------------------

class TestDealTrigger:
    @pytest.mark.asyncio
    async def test_below_target_is_deal(self):
        """target_price fornecida e best <= target → deal com savings_pct correto."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(
            validated=[_validated("kabum", 900.0)],
            target_price=1000.0,
            analysis={"avg_price_validated": 1000.0},
        ))
        deal = out["deal"]
        assert deal.is_deal is True
        assert deal.best_store_id == "kabum"
        assert deal.best_price == 900.0
        assert deal.target_price == 1000.0
        assert deal.savings_pct == 10.0  # (1000-900)/1000
        assert deal.discount_pct == 10.0  # (1000-900)/1000
        assert deal.summary  # resumo gerado (template, LLM off)

    @pytest.mark.asyncio
    async def test_below_threshold_no_target_is_deal(self):
        """Sem target: best <= history_avg * (1 - 5%) → deal."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(
            validated=[_validated("pichau", 940.0)],
            target_price=None,
            analysis={"avg_price_validated": 1000.0},  # 940 <= 950
        ))
        deal = out["deal"]
        assert deal.is_deal is True
        assert deal.best_price == 940.0
        assert deal.savings_pct is None  # sem target
        assert deal.discount_pct == 6.0  # (1000-940)/1000

    @pytest.mark.asyncio
    async def test_above_both_not_deal(self):
        """best acima do target e acima do threshold → não é deal."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(
            validated=[_validated("kabum", 1100.0)],
            target_price=1000.0,
            analysis={"avg_price_validated": 1000.0},
        ))
        deal = out["deal"]
        assert deal.is_deal is False
        assert deal.best_price == 1100.0
        assert deal.savings_pct == -10.0  # preço acima do alvo → economia negativa
        assert deal.discount_pct == -10.0  # preço acima da média

    @pytest.mark.asyncio
    async def test_no_target_above_threshold_not_deal(self):
        """Sem target e best acima do threshold → não é deal."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(
            validated=[_validated("kabum", 990.0)],
            target_price=None,
            analysis={"avg_price_validated": 1000.0},  # 990 > 950
        ))
        assert out["deal"].is_deal is False


# --- seleção do melhor preço ---------------------------------------------------

class TestBestPriceSelection:
    @pytest.mark.asyncio
    async def test_min_over_validated_available(self):
        """best_price = mínimo entre validados com available=True."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(
            validated=[
                _validated("kabum", 950.0),
                _validated("pichau", 899.0),
                _validated("terabyte", 920.0),
            ],
            target_price=1000.0,
        ))
        deal = out["deal"]
        assert deal.is_deal is True
        assert deal.best_price == 899.0
        assert deal.best_store_id == "pichau"

    @pytest.mark.asyncio
    async def test_unavailable_excluded(self):
        """available=False não entra na seleção."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(
            validated=[
                _validated("kabum", 500.0, available=False),
                _validated("pichau", 950.0),
            ],
            target_price=1000.0,
        ))
        deal = out["deal"]
        assert deal.best_price == 950.0
        assert deal.best_store_id == "pichau"

    @pytest.mark.asyncio
    async def test_flagged_suspicious_excluded(self):
        """Entradas marcadas como suspeitas não contam para o deal."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(
            validated=[
                _validated("kabum", 500.0, flagged_suspicious=True),
                _validated("pichau", 950.0),
            ],
            target_price=1000.0,
        ))
        deal = out["deal"]
        assert deal.best_price == 950.0
        assert deal.best_store_id == "pichau"

    @pytest.mark.asyncio
    async def test_tie_first_in_store_display_order(self):
        """Empate de preço → primeira store em ordem de STORE_DISPLAY_NAMES."""
        node = DealNode(llm_client=None)
        # pichau aparece antes de terabyte em STORE_DISPLAY_NAMES
        out = await node.run(_state(
            validated=[
                _validated("terabyte", 900.0),
                _validated("pichau", 900.0),
            ],
            target_price=1000.0,
        ))
        deal = out["deal"]
        assert deal.is_deal is True
        assert deal.best_price == 900.0
        assert deal.best_store_id == "pichau"


# --- edge cases ----------------------------------------------------------------

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_validated_not_deal(self):
        """validated vazio → is_deal=false, sem exceção, summary explica."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(validated=[], target_price=1000.0))
        deal = out["deal"]
        assert deal.is_deal is False
        assert deal.best_price is None
        assert deal.best_store_id is None
        assert "Nenhum preço confiável" in deal.summary

    @pytest.mark.asyncio
    async def test_empty_validated_with_errors_mentions_errors(self):
        """validated vazio com erros → summary cita stores com erro."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(
            validated=[],
            target_price=1000.0,
            errors=[{"node": "scraper", "iteration": 1, "error": "timeout"}],
        ))
        assert "stores com erro: 1" in out["deal"].summary

    @pytest.mark.asyncio
    async def test_no_history_no_target_not_deal(self):
        """history_avg=None e sem target → is_deal=false, summary indica falta de baseline."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(
            validated=[_validated("kabum", 900.0)],
            target_price=None,
            analysis={},  # sem avg_price_validated
        ))
        deal = out["deal"]
        assert deal.is_deal is False
        assert deal.best_price == 900.0
        assert "baseline" in deal.summary
        assert deal.discount_pct is None

    @pytest.mark.asyncio
    async def test_target_as_string(self):
        """target_price como string numérica é resolvida."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(
            validated=[_validated("kabum", 900.0)],
            target_price="1000.0",
        ))
        deal = out["deal"]
        assert deal.is_deal is True
        assert deal.target_price == 1000.0


# --- resumo --------------------------------------------------------------------

class TestSummary:
    @pytest.mark.asyncio
    async def test_llm_off_uses_template(self):
        """LLM off → template determinístico."""
        node = DealNode(llm_client=None)
        out = await node.run(_state(
            validated=[_validated("kabum", 900.0)],
            target_price=1000.0,
            analysis={"avg_price_validated": 1000.0},
        ))
        summary = out["deal"].summary
        assert summary.startswith("**Oportunidade detectada**")
        assert "RTX 4060" in summary
        assert "900.00" in summary

    @pytest.mark.asyncio
    async def test_llm_generates_summary(self):
        """LLM mockado → resumo do LLM é usado."""
        client = AsyncMock()
        client.chat = AsyncMock(return_value="Achadão! RTX 4060 por R$ 900 na Kabum.")
        node = DealNode(llm_client=client)
        out = await node.run(_state(
            validated=[_validated("kabum", 900.0)],
            target_price=1000.0,
            analysis={"avg_price_validated": 1000.0},
        ))
        assert out["deal"].summary == "Achadão! RTX 4060 por R$ 900 na Kabum."
        client.chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_template(self):
        """LLM falha → template determinístico (não derruba o run)."""
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=RuntimeError("llm down"))
        node = DealNode(llm_client=client)
        out = await node.run(_state(
            validated=[_validated("kabum", 900.0)],
            target_price=1000.0,
            analysis={"avg_price_validated": 1000.0},
        ))
        assert out["deal"].summary.startswith("**Oportunidade detectada**")
