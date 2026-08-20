"""
db/repositories/selector_repo.py — Overrides de seletor (self-healing, Inc 6).

Um override é uma **otimização**, nunca um requisito: qualquer erro de DB degrada
para ``None``/no-op com log, sem afetar o scrape (o scraper usa o seletor default
de ``SELECTORS`` quando não há override confiável).
"""

from __future__ import annotations

import logging
from typing import Optional

from db.database import get_db

logger = logging.getLogger(__name__)

_COLS = "id, store_id, element, selector, source, validated_at, success_count, failure_count"


def _to_dict(r) -> dict:
    return {
        "id": r["id"],
        "store_id": r["store_id"],
        "element": r["element"],
        "selector": r["selector"],
        "source": r["source"],
        "validated_at": r["validated_at"],
        "success_count": r["success_count"],
        "failure_count": r["failure_count"],
    }


async def get_override(store_id: str, element: str) -> Optional[dict]:
    """Retorna o override vigente para (store_id, element) ou ``None``.

    DB error → ``None`` com log (override é otimização, nunca requisito).
    """
    try:
        async with get_db() as db:
            rows = await db.execute_fetchall(
                f"SELECT {_COLS} FROM selector_overrides WHERE store_id = ? AND element = ?",
                (store_id, element),
            )
        return _to_dict(rows[0]) if rows else None
    except Exception as e:
        logger.warning(f"[selector_repo] get_override({store_id},{element}) falhou: {e}")
        return None


async def upsert_override(store_id: str, element: str, selector: str, source: str = "self_healing") -> None:
    """Cria ou atualiza o override; reseta contadores e marca ``validated_at``."""
    try:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO selector_overrides (store_id, element, selector, source, validated_at, success_count, failure_count)
                   VALUES (?, ?, ?, ?, datetime('now','localtime'), 0, 0)
                   ON CONFLICT(store_id, element) DO UPDATE SET
                       selector = excluded.selector,
                       source = excluded.source,
                       validated_at = excluded.validated_at,
                       success_count = 0,
                       failure_count = 0""",
                (store_id, element, selector, source),
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"[selector_repo] upsert_override({store_id},{element}) falhou: {e}")


async def record_outcome(store_id: str, element: str, success: bool) -> None:
    """Incrementa ``success_count`` ou ``failure_count`` do override vigente.

    Sem override → no-op (nada a contabilizar).
    """
    try:
        async with get_db() as db:
            col = "success_count" if success else "failure_count"
            await db.execute(
                f"UPDATE selector_overrides SET {col} = {col} + 1 WHERE store_id = ? AND element = ?",
                (store_id, element),
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"[selector_repo] record_outcome({store_id},{element},{success}) falhou: {e}")


async def invalidate_if_unreliable(store_id: str, element: str) -> bool:
    """Remove o override se ``failure_count > success_count + 1``.

    O ``+1`` é a **carência de graça** de um override recém-persistido: um único
    fracasso em um override com 0 acertos não o elimina imediatamente (evita
    churn quando o seletor recém-aprovado ainda não foi exercitado com sucesso).

    Returns:
        ``True`` se o override foi removido, ``False`` caso contrário (inclui inexistente).
    """
    try:
        async with get_db() as db:
            cursor = await db.execute(
                "DELETE FROM selector_overrides WHERE store_id = ? AND element = ? AND failure_count > success_count + 1",
                (store_id, element),
            )
            await db.commit()
            return (cursor.rowcount or 0) > 0
    except Exception as e:
        logger.warning(f"[selector_repo] invalidate_if_unreliable({store_id},{element}) falhou: {e}")
        return False


async def get_all_overrides() -> list[dict]:
    """Todos os overrides (para ``self_healing_status`` / depuração)."""
    try:
        async with get_db() as db:
            rows = await db.execute_fetchall(f"SELECT {_COLS} FROM selector_overrides ORDER BY store_id, element")
        return [_to_dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"[selector_repo] get_all_overrides falhou: {e}")
        return []


__all__ = [
    "get_override",
    "upsert_override",
    "record_outcome",
    "invalidate_if_unreliable",
    "get_all_overrides",
]
