"""Tests do MCP server (Inc 9).

Chama as funções tool **diretamente** (sem transport) com mocks: cada tool
delega para o código existente e, em erro, retorna ``{"success": False, ...}``
em vez de lançar. Também verifica que as 4 tools estão registradas no servidor.
"""

from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, patch

import pytest

from agents import mcp_server
from agents.state import AgentResult
from db.repositories.price_repo import PriceRecord


def _record(store_id: str = "kabum", price: float = 2999.0) -> PriceRecord:
    return PriceRecord(
        store_id=store_id,
        price=price,
        available=True,
        stock_label="Em estoque",
        url="https://www.kabum.com.br/p/x",
        scraped_at="2026-05-02 10:00:00",
        product_name="RTX 4060",
        search_term="rtx 4060",
    )


class TestRunAgent:
    async def test_delegates_and_returns_to_dict(self):
        result = AgentResult(
            product="RTX 4060",
            status="ok",
            results=[_record()],
            summary="Oferta: R$ 2.999,00 na KaBuM!",
            trace=[{"node": "scraper"}, {"node": "analyst"}, {"node": "deal"}],
            duration_ms=1234,
        )
        fake = AsyncMock(return_value=result)
        with patch("agents.orchestrator.run_agent_pipeline", fake):
            out = await mcp_server.run_agent("RTX 4060")
        fake.assert_awaited_once_with("RTX 4060", target_price=None)
        assert out["success"] is True
        assert out["product"] == "RTX 4060"
        assert out["status"] == "ok"
        assert out["duration_ms"] == 1234
        assert len(out["results"]) == 1

    async def test_target_price_forwarded(self):
        result = AgentResult(product="RTX 4060", status="ok")
        fake = AsyncMock(return_value=result)
        with patch("agents.orchestrator.run_agent_pipeline", fake):
            await mcp_server.run_agent("RTX 4060", target_price=3000.0)
        fake.assert_awaited_once_with("RTX 4060", target_price=3000.0)

    async def test_error_returns_error_dict(self):
        fake = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("agents.orchestrator.run_agent_pipeline", fake):
            out = await mcp_server.run_agent("RTX 4060")
        assert out["success"] is False
        assert "boom" in out["error"]


class TestGetLatest:
    async def test_delegates_and_serializes(self):
        fake = AsyncMock(return_value=[_record("kabum", 2999.0), _record("pichau", 2899.0)])
        with patch("toolkit.get_latest", fake):
            out = await mcp_server.get_latest("RTX 4060")
        fake.assert_awaited_once_with("RTX 4060")
        assert isinstance(out, list)
        assert out[0] == dataclasses.asdict(_record("kabum", 2999.0))
        assert out[1]["store_id"] == "pichau"

    async def test_error_returns_error_dict(self):
        fake = AsyncMock(side_effect=RuntimeError("db down"))
        with patch("toolkit.get_latest", fake):
            out = await mcp_server.get_latest("RTX 4060")
        assert out["success"] is False
        assert "db down" in out["error"]


class TestGetHistory:
    async def test_delegates_with_days(self):
        fake = AsyncMock(return_value=[_record()])
        with patch("toolkit.get_history", fake):
            out = await mcp_server.get_history("RTX 4060", days=14)
        fake.assert_awaited_once_with("RTX 4060", days=14)
        assert isinstance(out, list)
        assert out[0]["store_id"] == "kabum"

    async def test_default_days(self):
        fake = AsyncMock(return_value=[])
        with patch("toolkit.get_history", fake):
            await mcp_server.get_history("RTX 4060")
        fake.assert_awaited_once_with("RTX 4060", days=7)

    async def test_error_returns_error_dict(self):
        fake = AsyncMock(side_effect=RuntimeError("nope"))
        with patch("toolkit.get_history", fake):
            out = await mcp_server.get_history("RTX 4060")
        assert out["success"] is False
        assert "nope" in out["error"]


class TestSelfHealingStatus:
    async def test_lists_overrides(self):
        overrides = [
            {"store_id": "kabum", "element": "price", "selector": ".new-price"},
            {"store_id": "pichau", "element": "stock", "selector": ".stock-v2"},
        ]
        fake = AsyncMock(return_value=overrides)
        with patch("db.repositories.selector_repo.get_all_overrides", fake):
            out = await mcp_server.self_healing_status()
        fake.assert_awaited_once_with()
        assert out == overrides


class TestRelevanceStatus:
    async def test_lists_learned_terms(self):
        terms = [
            {"store_id": "kabum", "term": "adaptador", "source": "llm"},
            {"store_id": "amazon", "term": "cabo", "source": "llm"},
        ]
        fake = AsyncMock(return_value=terms)
        with patch("db.repositories.relevance_repo.get_all_terms", fake):
            out = await mcp_server.relevance_status()
        fake.assert_awaited_once_with()
        assert out == terms

    async def test_error_returns_error_dict(self):
        fake = AsyncMock(side_effect=RuntimeError("table missing"))
        with patch("db.repositories.relevance_repo.get_all_terms", fake):
            out = await mcp_server.relevance_status()
        assert out["success"] is False
        assert "table missing" in out["error"]

    async def test_error_returns_error_dict(self):
        fake = AsyncMock(side_effect=RuntimeError("table missing"))
        with patch("db.repositories.selector_repo.get_all_overrides", fake):
            out = await mcp_server.self_healing_status()
        assert out["success"] is False
        assert "table missing" in out["error"]


class TestRegistration:
    async def test_all_tools_registered(self):
        tools = await mcp_server.mcp.list_tools()
        names = {t.name for t in tools}
        assert {"run_agent", "get_latest", "get_history", "self_healing_status", "relevance_status"} <= names
