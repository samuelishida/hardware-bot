"""Re-export da taxonomia de erros do scraping para o MAS.

A taxonomia (``StoreOutcome``/``ScrapeErrorKind``/``looks_anti_bot``) vive em
``scrapers/errors.py`` — a camada de engine (``core.executor``) não deve depender
da camada MAS. Este módulo re-exporta os símbolos para os consumidores do MAS
(``agents/nodes/*``, testes).
"""

from __future__ import annotations

from scrapers.errors import (  # noqa: F401
    ScrapeErrorKind,
    StoreOutcome,
    looks_anti_bot,
)

__all__ = [
    "ScrapeErrorKind",
    "StoreOutcome",
    "looks_anti_bot",
]

