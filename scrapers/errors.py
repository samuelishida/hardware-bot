"""Taxonomia de erros do scraping.

Preenche o gap que ``core.executor`` deixa: as falhas eram logadas e **descartadas**.
Agora cada scraper retorna um :class:`StoreOutcome` com uma causa classificada, para
que o orquestrador decida se re-scrapeia (timeout/antibot) ou não.

Convenção de precedência na escolha da causa raiz: antibot > timeout > parse_error >
not_found > unknown — um site que exibe Cloudflare/captcha deve ser tratado como
antibot, mesmo quando o preço efetivamente não foi extraído.

Este módulo vive na camada ``scrapers/`` (não em ``agents/``) porque classifica
resultados de *scrapers* e é consumido por ``core.executor`` — a camada de engine
não deve depender da camada MAS. ``agents/errors.py`` re-exporta estes símbolos
para os consumidores do MAS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - evita import circular em runtime
    from scrapers.base import ScrapeResult


# Palavras-chave case-insensíveis de anti-bot detectadas no ``stock_label``/texto da página.
_ANTIBOT_PATTERNS = (r"cloudflare", r"captcha", r"verifique", r"suspeita", r"bloqueado")


class ScrapeErrorKind(str, Enum):
    """Causa do resultado de um scraper individual."""

    OK = "ok"                # extração bem-sucedida com preço válido (price is not None)
    TIMEOUT = "timeout"      # asyncio.TimeoutError no wait_for(90s)
    ANTI_BOT = "antibot"     # página exibe Cloudflare/captcha/verificação
    NOT_FOUND = "not_found"  # result.price is None and available=False (item não listado)
    PARSE_ERROR = "parse_error"  # preço/disponibilidade ilegíveis, mas a página existe
    UNKNOWN = "unknown"      # qualquer outra exceção

    @property
    def is_terminal(self) -> bool:
        """Causas que o Analista *não* deve revalidar (só log + trace)."""
        return self in {ScrapeErrorKind.ANTI_BOT, ScrapeErrorKind.TIMEOUT}


def looks_anti_bot(text):  # noqa: D401 -- small classifier helper
    """``True`` se ``text`` contém indícios de anti-bot (Cloudflare/captcha/...)."""
    if not text:
        return False
    low = str(text).lower()
    return any(re.search(p, low) for p in _ANTIBOT_PATTERNS)


@dataclass(frozen=True)
class StoreOutcome:
    """Resultado de *uma* store individual com sua causa classificada."""

    store_id: str
    result: "ScrapeResult | None" = None  # preço extraído (None se falhou)
    kind: ScrapeErrorKind = ScrapeErrorKind.UNKNOWN
    detail: str = ""


__all__ = [
    "ScrapeErrorKind",
    "StoreOutcome",
    "looks_anti_bot",
]
