"""Testes do ScraperNode (Inc 2).

Cobrem os critérios de done do plan.md Inc 2:
- todas as stores OK → outcomes com kind ok, raw_results populado, iteration=1, trace anexado
- 1 timeout → outcome com kind timeout presente
- 1 antibot (stock_label="Cloudflare") → outcome com kind antibot presente
- browser crash (executor lança) → outcomes=[] + errors preenchido + node **não** lança
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.errors import ScrapeErrorKind, StoreOutcome
from agents.nodes.scraper_node import ScraperNode
from scrapers.base import ScrapeResult


def _ok_outcome(store_id: str, price: float) -> StoreOutcome:
    return StoreOutcome(
        store_id=store_id,
        result=ScrapeResult(
            store_id=store_id,
            price=price,
            available=True,
            stock_label="Em estoque",
            url=f"https://{store_id}.example.com/item",
        ),
        kind=ScrapeErrorKind.OK,
    )


def _timeout_outcome(store_id: str) -> StoreOutcome:
    return StoreOutcome(
        store_id=store_id,
        result=None,
        kind=ScrapeErrorKind.TIMEOUT,
        detail="timed out after 90s",
    )


def _antibot_outcome(store_id: str) -> StoreOutcome:
    return StoreOutcome(
        store_id=store_id,
        result=None,
        kind=ScrapeErrorKind.ANTI_BOT,
        detail="Cloudflare challenge",
    )


def _state(**overrides) -> dict:
    base = {
        "product": "RTX 4060",
        "search_term": "RTX 4060",
        "target_price": None,
        "iteration": 0,
        "trace": [],
        "errors": [],
    }
    base.update(overrides)
    return base


@pytest.fixture
def node() -> ScraperNode:
    return ScraperNode()


@pytest.mark.asyncio
async def test_all_ok(node):
    outcomes = [
        _ok_outcome("kabum", 2999.0),
        _ok_outcome("pichau", 2899.0),
        _ok_outcome("terabyte", 3099.0),
    ]
    with (
        patch(
            "agents.nodes.scraper_node._scraper_classes",
            return_value=([object()], []),
        ),
        patch(
            "agents.nodes.scraper_node._scrape_product_detailed",
            new=AsyncMock(return_value=outcomes),
        ),
    ):
        update = await node.run(_state())

    assert update["iteration"] == 1
    assert update["outcomes"] == outcomes
    assert [o.store_id for o in update["outcomes"]] == ["kabum", "pichau", "terabyte"]
    assert all(o.kind is ScrapeErrorKind.OK for o in update["outcomes"])
    # raw_results = resultados não-None, na mesma ordem
    assert [r.store_id for r in update["raw_results"]] == ["kabum", "pichau", "terabyte"]
    assert update["raw_results"][0].price == 2999.0
    # trace anexado com resumo dos outcomes
    assert len(update["trace"]) == 1
    entry = update["trace"][0]
    assert entry["node"] == "scraper"
    assert entry["iteration"] == 1
    assert entry["n_outcomes"] == 3
    assert entry["kinds"] == ["ok", "ok", "ok"]


@pytest.mark.asyncio
async def test_one_timeout(node):
    outcomes = [
        _ok_outcome("kabum", 2999.0),
        _timeout_outcome("pichau"),
        _ok_outcome("terabyte", 3099.0),
    ]
    with (
        patch(
            "agents.nodes.scraper_node._scraper_classes",
            return_value=([object()], []),
        ),
        patch(
            "agents.nodes.scraper_node._scrape_product_detailed",
            new=AsyncMock(return_value=outcomes),
        ),
    ):
        update = await node.run(_state())

    kinds = [o.kind for o in update["outcomes"]]
    assert ScrapeErrorKind.TIMEOUT in kinds
    assert kinds.count(ScrapeErrorKind.OK) == 2
    # timeout não produz raw_result
    assert [r.store_id for r in update["raw_results"]] == ["kabum", "terabyte"]
    assert update["trace"][0]["kinds"] == ["ok", "timeout", "ok"]
    # o node não lança nem registra erro global
    assert update["iteration"] == 1


@pytest.mark.asyncio
async def test_one_antibot(node):
    outcomes = [
        _ok_outcome("kabum", 2999.0),
        _antibot_outcome("amazon"),
    ]
    with (
        patch(
            "agents.nodes.scraper_node._scraper_classes",
            return_value=([object()], []),
        ),
        patch(
            "agents.nodes.scraper_node._scrape_product_detailed",
            new=AsyncMock(return_value=outcomes),
        ),
    ):
        update = await node.run(_state())

    kinds = [o.kind for o in update["outcomes"]]
    assert ScrapeErrorKind.ANTI_BOT in kinds
    assert update["trace"][0]["kinds"] == ["ok", "antibot"]
    # antibot é terminal: o orquestrador (Inc 5) decide, não este node
    assert update["outcomes"][1].kind.is_terminal is True


@pytest.mark.asyncio
async def test_browser_crash_returns_empty_outcomes_and_error(node):
    state = _state()
    with (
        patch(
            "agents.nodes.scraper_node._scraper_classes",
            return_value=([object()], []),
        ),
        patch(
            "agents.nodes.scraper_node._scrape_product_detailed",
            new=AsyncMock(side_effect=RuntimeError("browser crashed")),
        ),
    ):
        # node nunca lança
        update = await node.run(state)

    assert update["outcomes"] == []
    assert update["raw_results"] == []
    assert update["iteration"] == 1
    assert update["trace"][0]["n_outcomes"] == 0
    # erro global registrado no estado (mutação) para o orquestrador
    assert len(state["errors"]) == 1
    err = state["errors"][0]
    assert err["node"] == "scraper"
    assert err["iteration"] == 1
    assert "browser crashed" in err["error"]


@pytest.mark.asyncio
async def test_iteration_increments_from_state(node):
    outcomes = [_ok_outcome("kabum", 100.0)]
    with (
        patch(
            "agents.nodes.scraper_node._scraper_classes",
            return_value=([object()], []),
        ),
        patch(
            "agents.nodes.scraper_node._scrape_product_detailed",
            new=AsyncMock(return_value=outcomes),
        ),
    ):
        update = await node.run(_state(iteration=1))

    # valor pós-incremento: iteração 2 do ciclo
    assert update["iteration"] == 2
    assert update["trace"][0]["iteration"] == 2


@pytest.mark.asyncio
async def test_trace_accumulates_across_iterations(node):
    outcomes = [_ok_outcome("kabum", 100.0)]
    with (
        patch(
            "agents.nodes.scraper_node._scraper_classes",
            return_value=([object()], []),
        ),
        patch(
            "agents.nodes.scraper_node._scrape_product_detailed",
            new=AsyncMock(return_value=outcomes),
        ),
    ):
        state = _state(
            iteration=1,
            trace=[{"node": "scraper", "iteration": 1, "n_outcomes": 1, "kinds": ["ok"]}],
        )
        update = await node.run(state)

    assert len(update["trace"]) == 2
    assert update["trace"][1]["iteration"] == 2
