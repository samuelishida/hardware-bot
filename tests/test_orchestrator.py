"""Testes do orquestrador (Inc 5).

Usa **nodes fake** (sem Playwright, sem LLM, sem DB) injetados via
``patch("agents.orchestrator._build_nodes")`` para validar a topologia do grafo:

* happy path: scraper → analyst → deal (status "ok");
* loop de feedback: 1ª iteração suspeito → re-scrape → 2ª ok → deal;
* cap de iterações: sempre suspeito → para em ``agent_max_iterations()``;
* node lança → status "error" (nunca propaga a exceção);
* ``AgentResult.duration_ms`` presente.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.nodes.deal_node import DealResult
from agents.orchestrator import build_graph, run_agent_pipeline


# --- nodes fake ----------------------------------------------------------------

class FakeScraper:
    """Devolve ``outcomes`` por chamada e incrementa ``iteration`` (pós-incremento)."""

    def __init__(self, outcomes_by_call: list):
        self.outcomes_by_call = outcomes_by_call
        self.calls = 0

    async def run(self, state: dict) -> dict:
        iteration = int(state.get("iteration", 0)) + 1
        idx = min(self.calls, len(self.outcomes_by_call) - 1)
        outcomes = self.outcomes_by_call[idx]
        self.calls += 1
        trace = list(state.get("trace", [])) + [{"node": "scraper", "iteration": iteration}]
        return {"raw_results": [], "outcomes": outcomes, "iteration": iteration, "trace": trace}


class FakeAnalyst:
    """Devolve updates (validated/suspicious/analysis) por chamada."""

    def __init__(self, updates_by_call: list):
        self.updates_by_call = updates_by_call
        self.calls = 0

    async def run(self, state: dict) -> dict:
        idx = min(self.calls, len(self.updates_by_call) - 1)
        upd = dict(self.updates_by_call[idx])
        self.calls += 1
        if "trace" not in upd:
            upd["trace"] = list(state.get("trace", [])) + [
                {"node": "analyst", "iteration": state.get("iteration", 0)}
            ]
        return upd


class FakeDeal:
    def __init__(self, deal=None):
        self.deal = deal
        self.calls = 0

    async def run(self, state: dict) -> dict:
        self.calls += 1
        return {"deal": self.deal}


def _validated(store_id: str, price: float) -> dict:
    return {
        "store_id": store_id,
        "price": price,
        "available": True,
        "url": f"https://{store_id}/x",
        "stock_label": "em estoque",
        "reason": "ok",
        "history_avg": 1000.0,
        "history_min": 900.0,
        "valid": True,
        "flagged_suspicious": False,
    }


def _suspicious(store_id: str, price: float, reason: str = "erro de leitura") -> dict:
    return {"store_id": store_id, "price": price, "reason": reason, "source": "deterministic"}


async def _run(scraper, analyst, deal, product="RTX 4060", target_price=None):
    # async para o bloco ``with patch`` permanecer ativo durante o ``await``
    # (se fosse sync, o patch sairia antes da coroutine executar → nodes reais).
    # _start_run/_finish_run mockados: observabilidade é coberta em test_run_repo.
    with (
        patch(
            "agents.orchestrator._build_nodes",
            return_value={"scraper": scraper, "analyst": analyst, "deal": deal},
        ),
        patch("agents.orchestrator._start_run", AsyncMock()),
        patch("agents.orchestrator._finish_run", AsyncMock()),
    ):
        return await run_agent_pipeline(product, target_price=target_price)


# --- testes ---------------------------------------------------------------------

class TestTopology:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        scraper = FakeScraper([["pichau"]])
        analyst = FakeAnalyst([{"validated": [_validated("pichau", 900.0)], "suspicious": []}])
        deal = FakeDeal(DealResult(is_deal=True, best_store_id="pichau", best_price=900.0,
                                   summary="deal"))
        result = await _run(scraper, analyst, deal, target_price=1000.0)

        assert scraper.calls == 1
        assert result.status == "ok"
        assert len(result.results) == 1
        assert result.results[0].store_id == "pichau"
        assert result.results[0].price == 900.0
        assert result.deal is not None
        assert result.deal.is_deal is True

    @pytest.mark.asyncio
    async def test_feedback_loop_rescrape_then_ok(self):
        # 1ª iteração: suspeito → re-scrape; 2ª: ok → deal
        scraper = FakeScraper([["pichau"], ["pichau"]])
        analyst = FakeAnalyst([
            {"validated": [], "suspicious": [_suspicious("pichau", 10.0)]},
            {"validated": [_validated("pichau", 900.0)], "suspicious": []},
        ])
        deal = FakeDeal(DealResult(is_deal=True, best_price=900.0, summary="deal"))
        result = await _run(scraper, analyst, deal, target_price=1000.0)

        assert scraper.calls == 2
        assert analyst.calls == 2
        assert result.status == "ok"
        assert len(result.results) == 1
        # trace acumula as duas iterações
        scraper_entries = [t for t in result.trace if t.get("node") == "scraper"]
        assert len(scraper_entries) == 2

    @pytest.mark.asyncio
    async def test_iteration_cap_stops_at_max(self):
        # sempre suspeito → para em agent_max_iterations() (default 2)
        scraper = FakeScraper([["pichau"], ["pichau"], ["pichau"]])
        analyst = FakeAnalyst([
            {"validated": [], "suspicious": [_suspicious("pichau", 10.0)]},
            {"validated": [], "suspicious": [_suspicious("pichau", 10.0)]},
            {"validated": [], "suspicious": [_suspicious("pichau", 10.0)]},
        ])
        deal = FakeDeal(DealResult(is_deal=False, summary="sem deal"))
        result = await _run(scraper, analyst, deal, target_price=1000.0)

        from agents.config import agent_max_iterations
        assert scraper.calls == agent_max_iterations()
        assert result.status == "error"  # zero validados
        assert result.results == []

    @pytest.mark.asyncio
    async def test_node_raises_becomes_error_status(self):
        class ExplodingScraper:
            async def run(self, state):
                raise RuntimeError("browser crash")

        analyst = FakeAnalyst([{"validated": [], "suspicious": []}])
        deal = FakeDeal(DealResult(is_deal=False, summary="sem preço"))
        result = await _run(ExplodingScraper(), analyst, deal)

        # exceção capturada (não propagada) → status "error", zero validados
        assert result.status == "error"
        assert result.results == []
        # o erro do node foi registrado no estado (visível via trace/summary)
        assert result.summary

    @pytest.mark.asyncio
    async def test_duration_ms_present(self):
        scraper = FakeScraper([["pichau"]])
        analyst = FakeAnalyst([{"validated": [_validated("pichau", 900.0)], "suspicious": []}])
        deal = FakeDeal(DealResult(is_deal=True, best_price=900.0, summary="deal"))
        result = await _run(scraper, analyst, deal)

        assert isinstance(result.duration_ms, int)
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_partial_status_when_validated_with_errors(self):
        # scraper ok mas analyst gera erro → validated presente + errors → "partial"
        class ScraperWithOutcome:
            async def run(self, state):
                iteration = int(state.get("iteration", 0)) + 1
                trace = list(state.get("trace", [])) + [{"node": "scraper", "iteration": iteration}]
                return {"raw_results": [], "outcomes": ["pichau"], "iteration": iteration, "trace": trace}

        class AnalystWithValidatedAndError:
            async def run(self, state):
                state.setdefault("errors", []).append({"node": "analyst", "error": "db timeout"})
                trace = list(state.get("trace", [])) + [{"node": "analyst"}]
                return {"validated": [_validated("pichau", 900.0)], "suspicious": [], "trace": trace}

        deal = FakeDeal(DealResult(is_deal=True, best_price=900.0, summary="deal"))
        result = await _run(ScraperWithOutcome(), AnalystWithValidatedAndError(), deal)

        assert result.status == "partial"
        assert len(result.results) == 1


class TestBuildGraph:
    def test_build_graph_returns_compiled(self):
        with patch("agents.orchestrator._build_nodes") as mock_nodes:
            mock_nodes.return_value = {
                "scraper": FakeScraper([[]]),
                "analyst": FakeAnalyst([{"validated": [], "suspicious": []}]),
                "deal": FakeDeal(),
            }
            graph = build_graph()
            assert hasattr(graph, "ainvoke")
