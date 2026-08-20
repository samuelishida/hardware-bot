"""
tests/test_agent_api.py — Unit tests for the ``agent`` command (Inc 7).

Cobre:
- ``_parse_agent_args`` (parse de ``<product> [target_price]``)
- ``cmd_agent`` (sucesso, target_price, exceção → ``_err``)
- dispatch em ``main()`` (argv → cmd_agent, init_db, erro de uso)

O pipeline real (``agents.orchestrator.run_agent_pipeline``) é mockado —
o import lazy dentro de ``cmd_agent`` resolve o atributo no módulo, então
patchamos ``agents.orchestrator.run_agent_pipeline``.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

import agent_api
from agents.nodes.analyst_node import ValidatedPrice
from agents.nodes.deal_node import DealResult
from agents.state import AgentResult


def _make_result(status: str = "ok") -> AgentResult:
    """AgentResult real (dataclasses reais) para ``to_dict()`` funcionar."""
    return AgentResult(
        product="RTX 4060",
        status=status,
        results=[
            ValidatedPrice(
                store_id="kabum",
                price=2999.0,
                available=True,
                url="https://kabum.com/rtx4060",
                stock_label="Em estoque",
                reason="dentro da faixa histórica",
                history_avg=3100.0,
                history_min=2850.0,
            )
        ],
        deal=DealResult(
            is_deal=True,
            best_store_id="kabum",
            best_price=2999.0,
            target_price=3000.0,
            discount_pct=3.2,
            savings_pct=0.03,
            summary="Oferta: R$ 2999,00 na KaBuM!",
        ),
        summary="Melhor preço: R$ 2999,00 (KaBuM!). Abaixo do alvo R$ 3000,00.",
        trace=[{"node": "start", "status": "init"}, {"node": "scraper", "status": "ok"}],
        duration_ms=1234,
    )


# --- _store_dict ---------------------------------------------------------------


class TestStoreDict:
    def test_includes_title(self):
        """Inc 1: _store_dict serializa title (default None)."""
        from scrapers.base import ScrapeResult

        r = ScrapeResult(store_id="kabum", price=100.0, available=True, stock_label="", url="")
        d = agent_api._store_dict(r)
        assert d["title"] is None

        r2 = ScrapeResult(store_id="kabum", price=100.0, available=True, stock_label="", url="", title="RTX 4060")
        d2 = agent_api._store_dict(r2)
        assert d2["title"] == "RTX 4060"


# --- _parse_agent_args ---------------------------------------------------------


class TestParseAgentArgs:
    def test_product_only(self):
        product, target = agent_api._parse_agent_args(["RTX 4060"])
        assert product == "RTX 4060"
        assert target is None

    def test_product_only_multi_tokens_numeric_last(self):
        # nome de produto termina em dígito → NÃO vira target (regressão do bug)
        product, target = agent_api._parse_agent_args(["RTX", "4060"])
        assert product == "RTX 4060"
        assert target is None

    def test_numeric_only_product(self):
        product, target = agent_api._parse_agent_args(["4060"])
        assert product == "4060"
        assert target is None

    def test_product_with_target(self):
        product, target = agent_api._parse_agent_args(["RTX 4060", "--", "3000"])
        assert product == "RTX 4060"
        assert target == 3000.0

    def test_product_with_float_target(self):
        product, target = agent_api._parse_agent_args(["RTX 4060", "--", "3000.50"])
        assert product == "RTX 4060"
        assert target == 3000.5

    def test_multiword_product(self):
        product, target = agent_api._parse_agent_args(
            ["RTX", "4060", "8GB", "--", "3000"]
        )
        assert product == "RTX 4060 8GB"
        assert target == 3000.0

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            agent_api._parse_agent_args([])

    def test_only_target_raises(self):
        # "-- 3000" sem produto
        with pytest.raises(ValueError):
            agent_api._parse_agent_args(["--", "3000"])

    def test_non_numeric_target_raises(self):
        with pytest.raises(ValueError):
            agent_api._parse_agent_args(["RTX 4060", "--", "abc"])

    def test_infinite_target_raises(self):
        with pytest.raises(ValueError):
            agent_api._parse_agent_args(["RTX 4060", "--", "9" * 400])


# --- cmd_agent -----------------------------------------------------------------


class TestCmdAgent:
    @pytest.mark.asyncio
    async def test_success_prints_full_json(self, capsys):
        fake = AsyncMock(return_value=_make_result())
        with patch("agents.orchestrator.run_agent_pipeline", fake):
            await agent_api.cmd_agent("RTX 4060")

        fake.assert_awaited_once_with("RTX 4060", target_price=None)
        out = json.loads(capsys.readouterr().out)
        assert out["success"] is True
        assert out["product"] == "RTX 4060"
        assert out["status"] == "ok"
        assert out["results"][0]["store_id"] == "kabum"
        assert out["results"][0]["price"] == 2999.0
        assert out["deal"]["is_deal"] is True
        assert out["deal"]["best_store_id"] == "kabum"
        assert "KaBuM" in out["summary"]
        assert out["trace"][0]["node"] == "start"
        assert out["duration_ms"] == 1234

    @pytest.mark.asyncio
    async def test_target_price_forwarded(self, capsys):
        fake = AsyncMock(return_value=_make_result())
        with patch("agents.orchestrator.run_agent_pipeline", fake):
            await agent_api.cmd_agent("RTX 4060", 3000.0)

        fake.assert_awaited_once_with("RTX 4060", target_price=3000.0)
        out = json.loads(capsys.readouterr().out)
        assert out["success"] is True

    @pytest.mark.asyncio
    async def test_error_status_still_success_true(self, capsys):
        """status='error' do pipeline → ainda success: true (pipeline rodou)."""
        fake = AsyncMock(return_value=_make_result(status="error"))
        with patch("agents.orchestrator.run_agent_pipeline", fake):
            await agent_api.cmd_agent("RTX 4060")

        out = json.loads(capsys.readouterr().out)
        assert out["success"] is True
        assert out["status"] == "error"

    @pytest.mark.asyncio
    async def test_exception_exits_1_with_error_json(self, capsys):
        fake = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("agents.orchestrator.run_agent_pipeline", fake):
            with pytest.raises(SystemExit) as exc:
                await agent_api.cmd_agent("RTX 4060")

        assert exc.value.code == 1
        out = json.loads(capsys.readouterr().out)
        assert out["success"] is False
        assert "boom" in out["error"]


# --- main() dispatch -----------------------------------------------------------


class TestMainDispatch:
    @pytest.mark.asyncio
    async def test_agent_command_success(self, capsys):
        fake = AsyncMock(return_value=_make_result())
        init_db = AsyncMock()
        with (
            patch("sys.argv", ["agent_api.py", "agent", "RTX 4060"]),
            patch("agents.orchestrator.run_agent_pipeline", fake),
            patch("db.database.init_db", init_db),
        ):
            await agent_api.main()

        init_db.assert_awaited_once()
        fake.assert_awaited_once_with("RTX 4060", target_price=None)
        out = json.loads(capsys.readouterr().out)
        assert out["success"] is True
        assert out["product"] == "RTX 4060"

    @pytest.mark.asyncio
    async def test_relevance_status_command(self, capsys):
        init_db = AsyncMock()
        terms = [{"store_id": "kabum", "term": "adaptador", "source": "llm"}]
        with (
            patch("sys.argv", ["agent_api.py", "relevance-status"]),
            patch("db.database.init_db", init_db),
            patch("db.repositories.relevance_repo.get_all_terms", new=AsyncMock(return_value=terms)),
        ):
            await agent_api.main()

        out = json.loads(capsys.readouterr().out)
        assert out["success"] is True
        assert out["relevance_overrides"] == terms

    @pytest.mark.asyncio
    async def test_agent_command_with_target_price(self, capsys):
        fake = AsyncMock(return_value=_make_result())
        init_db = AsyncMock()
        with (
            patch("sys.argv", ["agent_api.py", "agent", "RTX 4060", "--", "3000"]),
            patch("agents.orchestrator.run_agent_pipeline", fake),
            patch("db.database.init_db", init_db),
        ):
            await agent_api.main()

        fake.assert_awaited_once_with("RTX 4060", target_price=3000.0)
        out = json.loads(capsys.readouterr().out)
        assert out["success"] is True

    @pytest.mark.asyncio
    async def test_agent_command_pipeline_exception(self, capsys):
        fake = AsyncMock(side_effect=RuntimeError("grafo quebrou"))
        init_db = AsyncMock()
        with (
            patch("sys.argv", ["agent_api.py", "agent", "RTX 4060"]),
            patch("agents.orchestrator.run_agent_pipeline", fake),
            patch("db.database.init_db", init_db),
        ):
            with pytest.raises(SystemExit) as exc:
                await agent_api.main()

        assert exc.value.code == 1
        out = json.loads(capsys.readouterr().out)
        assert out["success"] is False
        assert "grafo quebrou" in out["error"]

    @pytest.mark.asyncio
    async def test_agent_command_missing_product(self, capsys):
        init_db = AsyncMock()
        with (
            patch("sys.argv", ["agent_api.py", "agent"]),
            patch("db.database.init_db", init_db),
        ):
            with pytest.raises(SystemExit) as exc:
                await agent_api.main()

        assert exc.value.code == 1
        out = json.loads(capsys.readouterr().out)
        assert out["success"] is False
        assert "agent requires" in out["error"]
