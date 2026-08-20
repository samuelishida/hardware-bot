"""
tests/test_analyst_node.py — Unit tests for agents/nodes/analyst_node.py (Inc 3).

Cobre as regras determinísticas (baseline histórico por store), o passo LLM
(só *adiciona* suspeita, nunca remove), os error paths e o output de estado.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import aiosqlite
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

from agents.errors import ScrapeErrorKind, StoreOutcome
from agents.nodes.analyst_node import AnalystNode
from scrapers.base import ScrapeResult


# --- helpers -------------------------------------------------------------------

def _ok_outcome(store_id: str, price: float, available: bool = True,
                url: str | None = None, stock_label: str | None = None) -> StoreOutcome:
    result = ScrapeResult(
        store_id=store_id,
        price=price,
        available=available,
        stock_label=stock_label,
        url=url,
    )
    return StoreOutcome(store_id=store_id, result=result, kind=ScrapeErrorKind.OK)


def _state(**overrides) -> dict:
    base = {
        "product": "RTX 4060",
        "search_term": "rtx-4060",
        "target_price": None,
        "iteration": 1,
        "trace": [],
        "errors": [],
    }
    base.update(overrides)
    return base


def _history(prices) -> list:
    """Fake history records — o node lê apenas ``.price`` via getattr."""
    return [SimpleNamespace(price=p) for p in prices]


def _patch_history(records) -> "patch":
    """Patch ``agents.nodes.analyst_node._get_price_history`` para devolver ``records``."""
    return patch(
        "agents.nodes.analyst_node._get_price_history",
        new=AsyncMock(return_value=records),
    )


# --- regras determinísticas ----------------------------------------------------

class TestDeterministicRules:
    @pytest.mark.asyncio
    async def test_normal_price_validated(self):
        """Preço dentro da faixa histórica → validado com baseline preenchido."""
        node = AnalystNode(llm_client=None)
        with _patch_history(_history([1000, 1000, 1000, 1000, 1000])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 950.0)]))
        assert len(out["validated"]) == 1
        v = out["validated"][0]
        assert v["store_id"] == "kabum"
        assert v["price"] == 950.0
        assert v["reason"] == "ok"
        assert v["history_avg"] == 1000.0
        assert v["history_min"] == 1000.0
        assert v["history_n"] == 5
        assert v["valid"] is True
        assert v["flagged_suspicious"] is False
        assert out["suspicious"] == []

    @pytest.mark.asyncio
    async def test_price_1pct_of_avg_rejected(self):
        """Preço 1% da média (n>=3) → suspeito determinístico."""
        node = AnalystNode(llm_client=None)
        with _patch_history(_history([1000, 1000, 1000])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 10.0)]))
        assert out["validated"] == []
        assert len(out["suspicious"]) == 1
        s = out["suspicious"][0]
        assert s["store_id"] == "kabum"
        assert s["price"] == 10.0
        assert s["source"] == "deterministic"
        assert s["reason"] == "erro de leitura provável: 1.0% da média"

    @pytest.mark.asyncio
    async def test_price_20x_avg_rejected(self):
        """Preço 20× a média (n>=3) → suspeito determinístico."""
        node = AnalystNode(llm_client=None)
        with _patch_history(_history([1000, 1000, 1000])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 20000.0)]))
        assert out["validated"] == []
        assert len(out["suspicious"]) == 1
        s = out["suspicious"][0]
        assert s["source"] == "deterministic"
        assert s["reason"] == "acima do plausível"

    @pytest.mark.asyncio
    async def test_non_positive_price_rejected(self):
        """price <= 0 → suspeito determinístico (regra 1, sempre aplica)."""
        node = AnalystNode(llm_client=None)
        with _patch_history(_history([])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 0.0)]))
        assert out["validated"] == []
        assert out["suspicious"][0]["reason"] == "preço não positivo"
        assert out["suspicious"][0]["source"] == "deterministic"

    @pytest.mark.asyncio
    async def test_no_history_validated_with_null_baseline(self):
        """Sem histórico (n=0) → validado com baseline nulo."""
        node = AnalystNode(llm_client=None)
        with _patch_history(_history([])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 950.0)]))
        assert len(out["validated"]) == 1
        v = out["validated"][0]
        assert v["reason"] == "sem histórico de baseline"
        assert v["history_avg"] is None
        assert v["history_min"] is None
        assert v["history_n"] == 0
        assert out["suspicious"] == []

    @pytest.mark.asyncio
    async def test_n_below_3_only_rule_1_applies(self):
        """n<3 → regras 2/3 não aplicam; preço 1% da média ainda valida."""
        node = AnalystNode(llm_client=None)
        with _patch_history(_history([1000, 1000])):  # n=2
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 10.0)]))
        assert len(out["validated"]) == 1
        assert out["validated"][0]["price"] == 10.0
        assert out["suspicious"] == []

    @pytest.mark.asyncio
    async def test_unavailable_skipped(self):
        """available=False → não valida nem marca suspeito."""
        node = AnalystNode(llm_client=None)
        with _patch_history(_history([1000, 1000, 1000])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 950.0, available=False)]))
        assert out["validated"] == []
        assert out["suspicious"] == []

    @pytest.mark.asyncio
    async def test_db_error_marks_suspicious(self):
        """Erro de consulta de histórico → store vira suspeito (não derruba o run)."""
        node = AnalystNode(llm_client=None)
        with patch(
            "agents.nodes.analyst_node._get_price_history",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 950.0)]))
        assert out["validated"] == []
        assert len(out["suspicious"]) == 1
        assert out["suspicious"][0]["reason"] == "erro de consulta"
        assert out["suspicious"][0]["source"] == "deterministic"


# --- passo LLM -----------------------------------------------------------------

class TestLLMPass:
    @pytest.mark.asyncio
    async def test_llm_rejects_moves_to_suspicious_with_source_llm(self):
        """LLM valid=false (confiança alta) → move para suspicious com source='llm'."""
        client = AsyncMock()
        client.chat_json = AsyncMock(
            return_value={"valid": False, "reason": "preço fora do padrão", "confidence": 0.9}
        )
        node = AnalystNode(llm_client=client)
        with _patch_history(_history([1000, 1000, 1000])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 950.0)]))
        assert out["validated"] == []
        assert len(out["suspicious"]) == 1
        s = out["suspicious"][0]
        assert s["source"] == "llm"
        assert s["reason"] == "preço fora do padrão"
        client.chat_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_low_confidence_keeps_validated(self):
        """LLM valid=false com confidence < 0.6 → loga mas mantém validada."""
        client = AsyncMock()
        client.chat_json = AsyncMock(
            return_value={"valid": False, "reason": "talvez", "confidence": 0.5}
        )
        node = AnalystNode(llm_client=client)
        with _patch_history(_history([1000, 1000, 1000])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 950.0)]))
        assert len(out["validated"]) == 1
        assert out["validated"][0]["store_id"] == "kabum"
        assert out["suspicious"] == []

    @pytest.mark.asyncio
    async def test_llm_off_degrades_to_deterministic(self):
        """llm_client=None → só regras determinísticas; validado permanece."""
        node = AnalystNode(llm_client=None)
        with _patch_history(_history([1000, 1000, 1000])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 950.0)]))
        assert len(out["validated"]) == 1
        assert out["suspicious"] == []

    @pytest.mark.asyncio
    async def test_llm_cannot_approve_deterministic_rejection(self):
        """Rejeição determinística nunca chega ao LLM; LLM só atua sobre validadas."""
        client = AsyncMock()
        client.chat_json = AsyncMock(return_value={"valid": True, "reason": "ok", "confidence": 0.9})
        node = AnalystNode(llm_client=client)
        # preço 1% da média → rejeitado determinístico (n>=3)
        with _patch_history(_history([1000, 1000, 1000])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 10.0)]))
        assert out["validated"] == []
        assert len(out["suspicious"]) == 1
        assert out["suspicious"][0]["source"] == "deterministic"
        # LLM não foi consultado para a store rejeitada deterministicamente
        client.chat_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_llm_unavailable_keeps_validated(self):
        """LLMUnavailable → mantém a decisão determinística (não derruba o run)."""
        from agents.llm import LLMUnavailable

        client = AsyncMock()
        client.chat_json = AsyncMock(side_effect=LLMUnavailable("llm down"))
        node = AnalystNode(llm_client=client)
        with _patch_history(_history([1000, 1000, 1000])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 950.0)]))
        assert len(out["validated"]) == 1
        assert out["suspicious"] == []


# --- output de estado ----------------------------------------------------------

class TestOutputShape:
    @pytest.mark.asyncio
    async def test_analysis_and_trace_populated(self):
        node = AnalystNode(llm_client=None)
        with _patch_history(_history([1000, 1000, 1000])):
            out = await node.run(
                _state(outcomes=[
                    _ok_outcome("kabum", 950.0),
                    _ok_outcome("pichau", 10.0),  # suspeito
                ])
            )
        analysis = out["analysis"]
        assert analysis["n_validated"] == 1
        assert analysis["n_suspicious"] == 1
        assert analysis["overall_min"] == 950.0
        assert analysis["avg_price_validated"] == 950.0
        assert analysis["per_store"]["kabum"] == {"avg": 1000.0, "min": 1000.0, "n": 3}
        assert analysis["per_store"]["pichau"] == {"avg": 1000.0, "min": 1000.0, "n": 3}
        # trace acumula
        assert len(out["trace"]) == 1
        t = out["trace"][0]
        assert t["node"] == "analyst"
        assert t["iteration"] == 1
        assert t["suspicious_stores"] == ["pichau"]

    @pytest.mark.asyncio
    async def test_only_ok_outcomes_considered(self):
        """Outcomes com kind != ok são ignorados pelo analista."""
        from agents.errors import ScrapeErrorKind

        timeout = StoreOutcome(
            store_id="olx", result=None, kind=ScrapeErrorKind.TIMEOUT
        )
        node = AnalystNode(llm_client=None)
        with _patch_history(_history([1000, 1000, 1000])):
            out = await node.run(_state(outcomes=[_ok_outcome("kabum", 950.0), timeout]))
        assert len(out["validated"]) == 1
        assert out["validated"][0]["store_id"] == "kabum"
        assert "olx" not in out["analysis"]["per_store"]


# --- DB real (in-memory) -------------------------------------------------------

@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """In-memory SQLite com price_history, patchado em price_repo.get_db."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("""
        CREATE TABLE price_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id     TEXT    NOT NULL,
            product_name TEXT    DEFAULT '',
            price        REAL,
            available    INTEGER,
            scraped_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
            data         TEXT    NOT NULL DEFAULT '{}'
        )
    """)
    await conn.commit()

    @asynccontextmanager
    async def mock_get_db():
        yield conn

    with patch("db.repositories.price_repo.get_db", mock_get_db):
        yield conn

    await conn.close()


class TestRealDatabase:
    @pytest.mark.asyncio
    async def test_price_100x_below_history_flagged_with_real_db(self, test_db):
        """Done criteria: com DB in-memory populado, preço 100× abaixo da média → suspeito."""
        from db.repositories.price_repo import insert_price

        # popula 5 observações históricas para kabum / RTX 4060
        for _ in range(5):
            await insert_price(
                store_id="kabum",
                price=1000.0,
                available=True,
                stock_label="Em estoque",
                url="https://kabum.com/rtx4060",
                product_name="RTX 4060",
                search_term="rtx-4060",
            )

        node = AnalystNode(llm_client=None)
        # preço 10.0 = 1% da média 1000 → 100× abaixo → suspeito determinístico
        out = await node.run(_state(outcomes=[_ok_outcome("kabum", 10.0)]))
        assert out["validated"] == []
        assert len(out["suspicious"]) == 1
        s = out["suspicious"][0]
        assert s["source"] == "deterministic"
        assert s["reason"] == "erro de leitura provável: 1.0% da média"
        # baseline veio do DB real
        assert out["analysis"]["per_store"]["kabum"]["n"] == 5
        assert out["analysis"]["per_store"]["kabum"]["avg"] == 1000.0
