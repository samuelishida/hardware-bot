"""PreçoBot Multi-Agent System (MAS) — LangGraph orchestrator with specialist agents.

Public API re-exports; see ``agents.state``, ``agents.llm`` and ``agents.config`` for details.
"""

from __future__ import annotations

# Inc 1 foundation ---------------------------------------------------------------
from agents.state import AgentResult, AgentState  # noqa: F401,E501 (re-export)
from agents.llm import LLMClient, LLMError, LLMUnavailable, get_llm_client  # noqa: F401,F822
from agents.config import agent_llm_mode, agent_max_iterations  # noqa: F401

# Inc 2-5 specialist nodes (imported lazily to avoid hard dep on langgraph) -----
try:  # pragma: no cover - optional if MAS not enabled at runtime
    from agents.nodes.analyst_node import AnalystNode, ValidatedPrice  # noqa: F401,F822
    from agents.nodes.deal_node import DealNode, DealResult  # noqa: F401,F822
except Exception:  # pragma: no cover - graceful if nodes not ready yet
    pass

__all__ = [
    "AgentState",
    "AgentResult",
    "LLMClient",
    "LLMError",
    "LLMUnavailable",
    "get_llm_client",
    "agent_llm_mode",
    "agent_max_iterations",
]