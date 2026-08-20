"""Scraper node do MAS (Inc 2).

Chama ``core.executor.scrape_product_detailed`` **uma única vez por iteração** e devolve os
:class:`StoreOutcome` classificados para o grafo. A decisão de re-scrapear (timeout/antibot/
preço suspeito) é do **orquestrador** (Inc 5, aresta condicional), não deste node: cada
iteração re-executa *todas* as stores (browser sequencial; custo aceito — ver plan.md Inc 5).

O node **nunca** lança: uma falha global (browser crash) vira ``errors`` + ``outcomes=[]``
e o grafo decide o que fazer a seguir.

Critical path: Inc 2 → `agents.nodes.scraper_node`. DAG dependência: core/executor.py.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.errors import StoreOutcome

logger = logging.getLogger(__name__)


class ScraperNode:
    """Agente Rastreador: scraping de todas as stores em uma iteração."""

    async def run(self, state: dict) -> dict[str, Any]:
        """Executa o scraping e devolve o update de estado do grafo.

        Returns:
            ``{"raw_results": list[ScrapeResult], "outcomes": list[StoreOutcome],
               "iteration": int, "trace": list[dict]}``

        ``iteration`` é o valor **pós-incremento** (começa em 0 no estado inicial); o
        orquestrador lê esse valor na aresta condicional para decidir se re-scrapeia.
        """
        search_term = state.get("search_term") or state.get("product") or ""
        iteration = int(state.get("iteration", 0)) + 1

        try:
            browser_classes, http_classes = _scraper_classes()
            outcomes: list[StoreOutcome] = await _scrape_product_detailed(
                browser_classes, http_classes, search_term
            )
        except Exception as e:  # browser crash / indisponibilidade → grafo decide
            logger.error(f"[scraper] falha global de scraping: {e}", exc_info=True)
            state.setdefault("errors", []).append(
                {"node": "scraper", "iteration": iteration, "error": str(e)}
            )
            outcomes = []

        raw_results = [o.result for o in outcomes if o.result is not None]

        trace = list(state.get("trace", []))
        trace.append(
            {
                "node": "scraper",
                "iteration": iteration,
                "n_outcomes": len(outcomes),
                "kinds": [_kind_value(o) for o in outcomes],
            }
        )

        return {
            "raw_results": raw_results,
            "outcomes": outcomes,
            "iteration": iteration,
            "trace": trace,
        }


def _scraper_classes():
    """Registry de scrapers (fonte única: ``scrapers/__init__.py``).

    Função de módulo para facilitar o patch em testes
    (``patch("agents.nodes.scraper_node._scraper_classes")``).
    """
    from scrapers import BROWSER_SCRAPERS, HTTP_SCRAPERS

    return list(BROWSER_SCRAPERS), list(HTTP_SCRAPERS)


async def _scrape_product_detailed(browser_classes, http_classes, search_term):
    """Indirection para ``core.executor.scrape_product_detailed`` (patchável em testes)."""
    from core.executor import scrape_product_detailed

    return await scrape_product_detailed(browser_classes, http_classes, search_term)


def _kind_value(outcome: StoreOutcome) -> str:
    """``kind`` como string serializável (para o trace)."""
    kind = getattr(outcome, "kind", "")
    return getattr(kind, "value", kind)


__all__ = ["ScraperNode", "StoreOutcome"]
