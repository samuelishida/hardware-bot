"""Orquestrador do MAS (Inc 5).

Constrói o grafo LangGraph e expõe a API pública ``run_agent_pipeline``.
**Todo o uso da API LangGraph fica apenas neste arquivo** (decisão de churn —
os nodes são funções puras ``async run(state) -> dict``).

Grafo:
    START → scraper → analyst → [conditional]
        suspicious não vazio and iteration < agent_max_iterations() → scraper
        senão → deal → END

``run_agent_pipeline`` **nunca lança**: qualquer falha (parse, node, timeout,
grafo) vira um ``AgentResult`` com ``status`` adequado. O LLM é injetado nos
nodes quando ``agent_llm_mode() != "off"``; em ``auto``/``on`` com LLM fora,
degrada para determinístico (log).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agents.config import agent_llm_mode, agent_max_iterations
from agents.llm import get_llm_client
from agents.nodes.analyst_node import AnalystNode, ValidatedPrice
from agents.nodes.deal_node import DealNode
from agents.nodes.scraper_node import ScraperNode
from agents.state import AgentResult, make_initial_state
from core.product_manager import ProductManager

logger = logging.getLogger(__name__)

# timeouts por node (s) — scraper é o mais lento (browser)
SCRAPER_TIMEOUT = 150.0
OTHER_TIMEOUT = 60.0


class _GraphState(TypedDict, total=False):
    """Schema do grafo (cada chave = um canal com reducer last-value-wins)."""

    product: str
    search_term: str
    target_price: float | None
    raw_results: list
    outcomes: list
    validated: list
    suspicious: list
    analysis: dict
    deal: object
    summary: str
    iteration: int
    errors: list
    trace: list


# --- construção do grafo -------------------------------------------------------

def _build_nodes() -> dict:
    """Instancia os nodes, injetando o LLM client quando o modo != 'off'.

    Função de módulo para facilitar o patch em testes
    (``patch("agents.orchestrator._build_nodes")``).
    """
    llm_client = None
    if agent_llm_mode() != "off":
        try:
            llm_client = get_llm_client()
        except Exception as e:  # LLM fora → degrada para determinístico
            logger.warning(f"[orchestrator] LLM indisponível ({e}); seguindo determinístico.")
            llm_client = None
    return {
        "scraper": ScraperNode(),
        "analyst": AnalystNode(llm_client=llm_client),
        "deal": DealNode(llm_client=llm_client),
    }


def _safe_update(node_name: str, state: dict) -> dict:
    """Update mínimo para manter o grafo andando após a falha de um node."""
    if node_name == "scraper":
        # incrementa iteration para não loopar; outcomes vazios → analyst → deal
        return {"outcomes": [], "raw_results": [], "iteration": int(state.get("iteration", 0)) + 1}
    if node_name == "analyst":
        return {"validated": [], "suspicious": [], "analysis": {}}
    return {"deal": None}


def _wrap_node(node, node_name: str, timeout: float):
    """Wrapper de node: timeout por node + captura de exceção (nunca lança)."""

    async def wrapper(state: dict) -> dict:
        iteration = int(state.get("iteration", 0))
        try:
            return await asyncio.wait_for(node.run(state), timeout=timeout)
        except asyncio.TimeoutError:
            err = {"node": node_name, "iteration": iteration, "error": f"timeout após {timeout:.0f}s"}
            logger.error(f"[orchestrator] {node_name} excedeu o timeout: {err}")
            state.setdefault("errors", []).append(err)
            return _safe_update(node_name, state)
        except Exception as e:
            err = {"node": node_name, "iteration": iteration, "error": str(e)}
            logger.error(f"[orchestrator] {node_name} falhou: {err}", exc_info=True)
            state.setdefault("errors", []).append(err)
            return _safe_update(node_name, state)

    wrapper.__name__ = f"node_{node_name}"
    return wrapper


def _route_after_analyst(state: dict) -> str:
    """Aresta condicional: re-scrape se há suspeitos e ainda há iterações.

    Lê o estado **pós-update** do analyst (iteration já incrementado pelo scraper).
    """
    suspicious = state.get("suspicious", [])
    iteration = int(state.get("iteration", 0))
    if suspicious and iteration < agent_max_iterations():
        return "scraper"
    return "deal"


def build_graph():
    """Constrói e compila o grafo LangGraph do MAS."""
    nodes = _build_nodes()
    g = StateGraph(_GraphState)
    g.add_node("scraper", _wrap_node(nodes["scraper"], "scraper", SCRAPER_TIMEOUT))
    g.add_node("analyst", _wrap_node(nodes["analyst"], "analyst", OTHER_TIMEOUT))
    g.add_node("deal", _wrap_node(nodes["deal"], "deal", OTHER_TIMEOUT))
    g.add_edge(START, "scraper")
    g.add_edge("scraper", "analyst")
    g.add_conditional_edges(
        "analyst",
        _route_after_analyst,
        {"scraper": "scraper", "deal": "deal"},
    )
    g.add_edge("deal", END)
    return g.compile()


# --- API pública ---------------------------------------------------------------

async def run_agent_pipeline(product: str, target_price: float | None = None) -> AgentResult:
    """Executa o pipeline multi-agente e devolve um ``AgentResult`` (nunca lança).

    ``status``:
      * ``"ok"``      — ≥1 validado e sem errors;
      * ``"partial"`` — ≥1 validado com errors (ou LLM-degraded);
      * ``"error"``   — zero validados.

    Observabilidade (Inc 8): cada execução grava 1 linha em ``agent_runs``
    (``start_run`` no início, ``finish_run`` no ``finally``). Falha de DB nunca
    derruba o run.
    """
    started = time.time()
    run_id = uuid.uuid4().hex[:12]
    await _start_run(run_id, str(product))
    result: AgentResult | None = None
    try:
        try:
            parsed = ProductManager.parse_product_name(product)
        except Exception as e:
            logger.error(f"[orchestrator] parse_product_name falhou: {e}")
            result = AgentResult(
                product=str(product),
                status="error",
                results=[],
                deal=None,
                summary=f"Falha ao interpretar o produto: {e}",
                trace=[],
                duration_ms=int((time.time() - started) * 1000),
            )
            return result

        initial = make_initial_state(
            parsed.name, search_term=parsed.search_term, target_price=target_price
        )
        try:
            graph = build_graph()
            final_state = await graph.ainvoke(dict(initial))
        except Exception as e:
            logger.error(f"[orchestrator] grafo falhou: {e}", exc_info=True)
            result = AgentResult(
                product=parsed.name,
                status="error",
                results=[],
                deal=None,
                summary=f"Falha no orquestrador: {e}",
                trace=list(initial.get("trace", [])),
                duration_ms=int((time.time() - started) * 1000),
            )
            return result

        result = _build_result(parsed.name, final_state, started)
        return result
    finally:
        await _finish_run(run_id, result, started)


async def _start_run(run_id: str, product: str) -> None:
    """Registra o início do run em ``agent_runs``. Nunca lança (observabilidade)."""
    try:
        from db.repositories.run_repo import start_run

        await start_run(run_id, product)
    except Exception as e:
        logger.warning(f"[orchestrator] start_run falhou: {e}")


async def _finish_run(run_id: str, result: AgentResult | None, started: float) -> None:
    """Finaliza o run em ``agent_runs``. Nunca lança (observabilidade).

    ``result=None`` → run abortado antes de produzir resultado (``finished_at``
    fica nulo; leitura o marca como "incomplete").
    """
    if result is None:
        return
    try:
        from db.repositories.run_repo import finish_run

        await finish_run(
            run_id,
            result.status,
            list(result.trace),
            result.summary if result.status == "error" else None,
            result.duration_ms,
        )
    except Exception as e:
        logger.warning(f"[orchestrator] finish_run falhou: {e}")


def _to_validated_price(v: dict) -> ValidatedPrice:
    """Converte o dict validado (tráfego do grafo) na view tipada ``ValidatedPrice``."""
    return ValidatedPrice(
        store_id=v.get("store_id"),
        price=v.get("price"),
        available=v.get("available", True),
        url=v.get("url"),
        stock_label=v.get("stock_label"),
        reason=v.get("reason", ""),
        history_avg=v.get("history_avg"),
        history_min=v.get("history_min"),
    )


def _build_result(product: str, state: dict, started: float) -> AgentResult:
    """Monta o ``AgentResult`` a partir do estado final do grafo."""
    validated = state.get("validated", []) or []
    errors = state.get("errors", []) or []
    deal = state.get("deal")
    trace = state.get("trace", []) or []

    if validated and not errors:
        status = "ok"
    elif validated:
        status = "partial"
    else:
        status = "error"

    summary = ""
    if deal is not None:
        summary = getattr(deal, "summary", "") or ""
    if not summary and status == "error":
        summary = "Nenhum preço confiável nesta rodada."

    return AgentResult(
        product=product,
        status=status,
        results=[_to_validated_price(v) for v in validated],
        deal=deal,
        summary=summary or None,
        trace=list(trace),
        duration_ms=int((time.time() - started) * 1000),
    )


__all__ = ["build_graph", "run_agent_pipeline"]
