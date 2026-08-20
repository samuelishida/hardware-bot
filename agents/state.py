"""Estado do grafo e payloads tipados para o MAS (Inc 1).

As formas de dados pesadas criadas pelos increments seguintes são importadas com
guarda ``TYPE_CHECKING`` para evitar ciclos: ``StoreOutcome`` (Inc 2),
``ValidatedPrice`` (Inc 3) e ``DealResult`` (Inc 4). Também expõe o helper
``safe_float`` compartilhado (conversão tolerante a vírgula/NaN).
Os campos da TypedDict usam anotações de string lazy para que a importação nunca
ocorra em tempo de execução.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - runtime guard contra ciclos
    from agents.nodes.scraper_node import StoreOutcome  # type: ignore
    from agents.nodes.analyst_node import ValidatedPrice  # type: ignore
    from agents.nodes.deal_node import DealResult


@dataclass
class AgentResult:
    """Resultado final entregue ao caller do MAS."""

    product: str
    status: str            # "ok" | "partial" | "error"
    results: list["ValidatedPrice"] = field(default_factory=list)  # type: ignore[name-defined]
    deal: "DealResult | None" = None        # type: ignore[name-defined]
    summary: str | None = None              # type: ignore[assignment]
    trace: list[dict] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict:
        """Serializar para JSON (agent_api.py / MCP)."""
        return {
            "success": True,
            "product": self.product,
            "status": self.status,
            "results": [vars(r) for r in self.results],  # dataclass-safe dicts
            "deal": vars(self.deal) if self.deal is not None else None,
            "summary": self.summary,
            "trace": list(self.trace),
            "duration_ms": self.duration_ms,
        }


# Estado mutável do grafo LangGraph. ``total=False`` permite que cada node retorne
# um update parcial (padrão clássico de grafos em LangGraph).
class AgentState(dict):  # type: ignore[override] -- dict-based graph state
    """Estado do MAS, modelado como um dicionário com chaves tipadas.

    Os nodes retornam ``dict`` parciais que são mesclados pelo grafo; os campos
    list/dict começam vazios automaticamente quando acessados via `defaultdict`-like
    (ver ``build_graph``).
    """

    def __init__(self, **kwargs) -> None:  # type: ignore[override]
        super().__init__()
        for k, v in kwargs.items():
            self[k] = v

    @property
    def product(self) -> str:           # type: ignore[prop-decorator]
        return self.get("product", "")   # type: ignore[return-value]

    @property
    def search_term(self) -> str:       # type: ignore[prop-decorator]
        return self.get("search_term", "")  # type: ignore[return-value]

    @property
    def target_price(self):            # type: ignore[prop-decorator]
        return self.get("target_price")   # type: ignore[return-value]

    @property
    def iteration(self) -> int:         # type: ignore[prop-decorator]
        return self.get("iteration", 0)  # type: ignore[return-value]


def make_initial_state(product: str, *, search_term: str | None = None,
                       target_price: float | None = None) -> AgentState:
    """Estado inicial do grafo (antes de START)."""
    return AgentState(
        product=product,
        search_term=search_term or "",
        target_price=target_price,
        raw_results=[],
        outcomes=[],
        validated=[],
        suspicious=[],
        analysis={},
        deal=None,
        summary="",
        iteration=0,
        errors=[],
        trace=[{"node": "start", "started_at": time.time(), "status": "init"}],
    )


# Chaves reconhecidas pelo grafo; usadas para validação leve de updates.
GRAPH_KEYS = (
    "product", "search_term", "target_price", "raw_results", "outcomes",
    "validated", "suspicious", "analysis", "deal", "summary", "iteration",
    "errors", "trace",
)


def safe_float(x):
    """Converte para float tolerando vírgula decimal; ``None``/vazio/NaN → ``None``.

    Helper compartilhado entre AnalystNode e DealNode (evita duplicação).
    """
    try:
        if x is None or (isinstance(x, str) and not str(x).strip()):
            return None
        f = float(str(x).replace(",", "."))
        return f if f == f else None  # NaN guard
    except (TypeError, ValueError):
        return None
