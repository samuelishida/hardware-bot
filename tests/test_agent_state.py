"""tests/test_agent_state.py — Inc 1: AgentState + AgentResult.

Cobre o contrato do estado do grafo e a serialização do resultado final,
sem depender de LLM, browser ou DB.
"""

from __future__ import annotations

import pytest

from agents.state import (
    AgentResult,
    AgentState,
    GRAPH_KEYS,
    make_initial_state,
)
from agents.nodes.analyst_node import ValidatedPrice
from agents.nodes.deal_node import DealResult


class TestMakeInitialState:
    def test_contains_all_graph_keys(self):
        state = make_initial_state("ryzen 5700x3d")
        for key in GRAPH_KEYS:
            assert key in state, f"chave {key!r} ausente no estado inicial"

    def test_defaults(self):
        state = make_initial_state("prod", search_term="term", target_price=100.0)
        assert state["product"] == "prod"
        assert state["search_term"] == "term"
        assert state["target_price"] == 100.0
        assert state["iteration"] == 0
        assert state["raw_results"] == []
        assert state["outcomes"] == []
        assert state["validated"] == []
        assert state["suspicious"] == []
        assert state["analysis"] == {}
        assert state["deal"] is None
        assert state["errors"] == []
        assert isinstance(state["trace"], list) and state["trace"]

    def test_search_term_defaults_empty(self):
        state = make_initial_state("prod")
        assert state["search_term"] == ""
        assert state["target_price"] is None


class TestAgentStateProperties:
    def test_property_accessors(self):
        state = make_initial_state("prod", target_price=42.0)
        assert state.product == "prod"
        assert state.search_term == ""
        assert state.target_price == 42.0
        assert state.iteration == 0

    def test_missing_keys_return_safe_defaults(self):
        state = AgentState()
        assert state.product == ""
        assert state.search_term == ""
        assert state.target_price is None
        assert state.iteration == 0


class TestAgentResult:
    def test_to_dict_shape(self):
        res = AgentResult(
            product="prod",
            status="ok",
            results=[],
            deal=None,
            summary="resumo",
            trace=[{"node": "start"}],
            duration_ms=123,
        )
        d = res.to_dict()
        assert d["success"] is True
        assert d["product"] == "prod"
        assert d["status"] == "ok"
        assert d["results"] == []
        assert d["deal"] is None
        assert d["summary"] == "resumo"
        assert d["trace"] == [{"node": "start"}]
        assert d["duration_ms"] == 123

    def test_to_dict_serializes_dataclass_results(self):
        res = AgentResult(
            product="p",
            status="ok",
            results=[ValidatedPrice(store_id="kabum", price=100.0)],
        )
        d = res.to_dict()
        assert d["results"] == [{"store_id": "kabum", "price": 100.0, "available": True, "url": None, "stock_label": None, "reason": "", "history_avg": None, "history_min": None}]

    def test_to_dict_serializes_deal(self):
        res = AgentResult(
            product="p",
            status="ok",
            deal=DealResult(is_deal=True, best_store_id="kabum", best_price=99.0),
        )
        d = res.to_dict()
        assert d["deal"]["is_deal"] is True
        assert d["deal"]["best_store_id"] == "kabum"
        assert d["deal"]["best_price"] == 99.0


class TestGraphKeys:
    def test_graph_keys_is_tuple_of_strings(self):
        assert isinstance(GRAPH_KEYS, tuple)
        assert all(isinstance(k, str) for k in GRAPH_KEYS)
        # sem duplicatas
        assert len(GRAPH_KEYS) == len(set(GRAPH_KEYS))
