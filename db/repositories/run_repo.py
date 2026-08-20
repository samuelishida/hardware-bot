"""
db/repositories/run_repo.py — Observabilidade do pipeline MAS (Inc 8).

Cada execução de ``run_agent_pipeline`` grava 1 linha em ``agent_runs``
(start → finish). Observabilidade **nunca derruba o run**: qualquer falha de
DB vira log, nunca exceção propagada.

Run abortado (Ctrl-C / timeout do hermes) fica com ``finished_at`` nulo —
``get_recent_runs`` o marca como ``"incomplete"`` (limpeza é fora de escopo).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from db.database import get_db

logger = logging.getLogger(__name__)


async def start_run(run_id: str, product: str) -> None:
    """Registra o início de um run (``finished_at`` nulo até ``finish_run``).

    Falha de gravação → log, nunca propaga.
    """
    try:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO agent_runs (run_id, product, started_at, status)
                   VALUES (?, ?, datetime('now','localtime'), 'running')""",
                (run_id, product),
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"[run_repo] start_run({run_id}) falhou: {e}")


async def finish_run(
    run_id: str,
    status: str,
    nodes: list[dict],
    error: Optional[str],
    duration_ms: int,
) -> None:
    """Finaliza o run: status, trace serializado, erro e duração.

    ``status``: ``ok`` | ``partial`` | ``error``. Falha de gravação → log,
    nunca propaga (observabilidade não derruba o run).
    """
    try:
        async with get_db() as db:
            await db.execute(
                """UPDATE agent_runs SET
                       finished_at = datetime('now','localtime'),
                       status = ?,
                       nodes_json = ?,
                       error = ?,
                       duration_ms = ?
                   WHERE run_id = ?""",
                (status, json.dumps(nodes, ensure_ascii=False), error, duration_ms, run_id),
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"[run_repo] finish_run({run_id}) falhou: {e}")


async def get_recent_runs(limit: int = 10) -> list[dict]:
    """Últimos runs, mais recente primeiro.

    Runs com ``finished_at`` nulo (abortados) ganham ``status="incomplete"``.
    Falha de leitura → ``[]`` com log.
    """
    try:
        limit = max(1, int(limit))  # clamp defensivo: limit < 1 quebraria o LIMIT
        async with get_db() as db:
            rows = await db.execute_fetchall(
                """SELECT run_id, product, started_at, finished_at, status,
                          nodes_json, error, duration_ms
                   FROM agent_runs
                   ORDER BY started_at DESC, id DESC
                   LIMIT ?""",
                (limit,),
            )
    except Exception as e:
        logger.warning(f"[run_repo] get_recent_runs({limit}) falhou: {e}")
        return []

    runs: list[dict] = []
    for r in rows:
        nodes: list[dict] = []
        if r["nodes_json"]:
            try:
                nodes = json.loads(r["nodes_json"])
            except (json.JSONDecodeError, TypeError):
                nodes = []
        runs.append(
            {
                "run_id": r["run_id"],
                "product": r["product"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "status": "incomplete" if r["finished_at"] is None else r["status"],
                "nodes": nodes,
                "error": r["error"],
                "duration_ms": r["duration_ms"],
            }
        )
    return runs
