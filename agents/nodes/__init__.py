"""Specialist MAS nodes (Inc 2-5). Import lazily to avoid hard dep on langgraph."""

from __future__ import annotations

try:
    from agents.nodes.scraper_node import ScraperNode, StoreOutcome  # noqa: F401,F822
except Exception:  # pragma: no cover - fallback if MAS not installed yet
    pass

try:
    from agents.nodes.analyst_node import (  # noqa: F401,F822
        AnalystNode,
        ValidatedPrice,
    )
except Exception:  # pragma: no cover - fallback if MAS not installed yet
    pass

try:
    from agents.nodes.deal_node import DealNode, DealResult  # noqa: F401,F822
except Exception:  # pragma: no cover - fallback if MAS not installed yet
    pass

__all__ = ["ScraperNode", "StoreOutcome", "AnalystNode", "ValidatedPrice", "DealNode", "DealResult"]
