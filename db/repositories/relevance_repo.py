"""db/repositories/relevance_repo.py — Termos de relevância aprendidos (self-healing).

Um termo aprendido é uma **otimização**, nunca um requisito: qualquer erro de DB
degrada para ``[]``/no-op com log, sem afetar o scrape (o scraper filtra só com
``ACCESSORY_TERMS`` quando não há termos aprendidos).
"""

from __future__ import annotations

import logging
import re
import unicodedata

from db.database import get_db

logger = logging.getLogger(__name__)


def _normalize(term: str) -> str:
    """Lowercase, remove diacríticos e colapsa pontuação/whitespace.

    Mesma forma usada por ``scrapers.relevance.is_relevant`` na leitura, para a
    chave UNIQUE deduplicar na mesma representação do matching.
    """
    s = (term or "").lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


async def get_terms(store_id: str) -> list[str]:
    """Termos de exclusão aprendidos para a store (override é otimização, nunca requisito)."""
    try:
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT term FROM relevance_overrides WHERE store_id = ? ORDER BY id",
                (store_id,),
            )
        return [r["term"] for r in rows]
    except Exception as e:
        logger.warning(f"[relevance_repo] get_terms({store_id}) falhou: {e}")
        return []


async def add_term(store_id: str, term: str, source: str = "llm") -> None:
    """Persiste um termo aprendido (idempotente via ``ON CONFLICT DO NOTHING``).

    Normaliza o termo (lowercase, sem acento, colapsa whitespace) para que a chave
    UNIQUE deduplique na mesma forma usada por ``is_relevant`` na leitura.
    """
    term = _normalize(term)
    if not term:
        return
    try:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO relevance_overrides (store_id, term, source)
                   VALUES (?, ?, ?)
                   ON CONFLICT(store_id, term) DO NOTHING""",
                (store_id, term, source),
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"[relevance_repo] add_term({store_id},{term}) falhou: {e}")


async def get_all_terms() -> list[dict]:
    """Todos os termos aprendidos (para ``relevance_status`` / depuração)."""
    try:
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT store_id, term, source, created_at FROM relevance_overrides ORDER BY store_id, id"
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"[relevance_repo] get_all_terms falhou: {e}")
        return []


__all__ = ["get_terms", "add_term", "get_all_terms"]