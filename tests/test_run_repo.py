"""
tests/test_run_repo.py — Unit tests for db/repositories/run_repo.py (Inc 8).

In-memory SQLite (mesmo padrão de test_repositories.py / test_selector_repo.py):
patch de ``db.repositories.run_repo.get_db`` com um asynccontextmanager que
yielda a conexão.

Cobre: start/finish/get_recent, ordenação, "incomplete" (finished_at nulo),
e o contrato de erro — ``finish_run`` com DB quebrado **não lança**.
"""

from __future__ import annotations

import json
import aiosqlite
import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import patch

from db.repositories.run_repo import start_run, finish_run, get_recent_runs


@asynccontextmanager
async def _broken_get_db():
    """Fake de ``get_db`` que quebra — para testar o contrato de erro (não lançar)."""
    raise RuntimeError("db fora do ar")
    yield  # pragma: no cover


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """In-memory DB com a tabela ``agent_runs``, patched no repo."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row

    await conn.execute(
        """
        CREATE TABLE agent_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      TEXT    NOT NULL,
            product     TEXT    NOT NULL,
            started_at  TEXT    NOT NULL,
            finished_at TEXT,
            status      TEXT    NOT NULL,
            nodes_json  TEXT,
            error       TEXT,
            duration_ms INTEGER
        )
        """
    )
    await conn.commit()

    @asynccontextmanager
    async def mock_get_db():
        yield conn

    with patch("db.repositories.run_repo.get_db", mock_get_db):
        yield conn
        await conn.close()


class TestStartRun:
    @pytest.mark.asyncio
    async def test_start_run_inserts_running_row(self, test_db):
        await start_run("abc123", "RTX 4060")

        rows = await test_db.execute_fetchall(
            "SELECT run_id, product, status, finished_at FROM agent_runs"
        )
        assert len(rows) == 1
        assert rows[0]["run_id"] == "abc123"
        assert rows[0]["product"] == "RTX 4060"
        assert rows[0]["status"] == "running"
        assert rows[0]["finished_at"] is None

    @pytest.mark.asyncio
    async def test_start_run_db_error_does_not_raise(self):
        """Falha de gravação → log, nunca propaga (observabilidade não derruba o run)."""

        with patch("db.repositories.run_repo.get_db", _broken_get_db):
            await start_run("abc123", "RTX 4060")  # não deve lançar


class TestFinishRun:
    @pytest.mark.asyncio
    async def test_finish_run_updates_row(self, test_db):
        await start_run("abc123", "RTX 4060")
        nodes = [{"node": "scraper", "status": "ok"}, {"node": "deal", "status": "ok"}]
        await finish_run("abc123", "ok", nodes, None, 1234)

        rows = await test_db.execute_fetchall(
            "SELECT status, finished_at, nodes_json, error, duration_ms FROM agent_runs"
        )
        assert rows[0]["status"] == "ok"
        assert rows[0]["finished_at"] is not None
        assert rows[0]["error"] is None
        assert rows[0]["duration_ms"] == 1234
        assert json.loads(rows[0]["nodes_json"]) == nodes

    @pytest.mark.asyncio
    async def test_finish_run_error_status_stores_error(self, test_db):
        await start_run("err1", "RTX 4060")
        await finish_run("err1", "error", [], "Nenhum preço confiável", 500)

        rows = await test_db.execute_fetchall(
            "SELECT status, error FROM agent_runs"
        )
        assert rows[0]["status"] == "error"
        assert rows[0]["error"] == "Nenhum preço confiável"

    @pytest.mark.asyncio
    async def test_finish_run_db_error_does_not_raise(self):
        """``finish_run`` com DB quebrado não lança (contrato do Inc 8)."""

        with patch("db.repositories.run_repo.get_db", _broken_get_db):
            await finish_run("abc123", "ok", [], None, 100)  # não deve lançar


class TestGetRecentRuns:
    @pytest.mark.asyncio
    async def test_get_recent_empty(self, test_db):
        assert await get_recent_runs() == []

    @pytest.mark.asyncio
    async def test_get_recent_returns_dicts(self, test_db):
        await start_run("r1", "RTX 4060")
        await finish_run("r1", "ok", [{"node": "scraper"}], None, 100)

        runs = await get_recent_runs()
        assert len(runs) == 1
        run = runs[0]
        assert run["run_id"] == "r1"
        assert run["product"] == "RTX 4060"
        assert run["status"] == "ok"
        assert run["finished_at"] is not None
        assert run["nodes"] == [{"node": "scraper"}]
        assert run["error"] is None
        assert run["duration_ms"] == 100

    @pytest.mark.asyncio
    async def test_get_recent_limit(self, test_db):
        for i in range(5):
            await start_run(f"r{i}", f"prod{i}")
            await finish_run(f"r{i}", "ok", [], None, i)

        runs = await get_recent_runs(limit=3)
        assert len(runs) == 3

    @pytest.mark.asyncio
    async def test_get_recent_most_recent_first(self, test_db):
        # started_at usa datetime('now','localtime') (segundos) → força ordem via id
        for i in range(3):
            await start_run(f"r{i}", f"prod{i}")
            await finish_run(f"r{i}", "ok", [], None, i)

        runs = await get_recent_runs(limit=10)
        # mais recente (maior id) primeiro
        assert runs[0]["run_id"] == "r2"
        assert runs[-1]["run_id"] == "r0"

    @pytest.mark.asyncio
    async def test_get_recent_aborted_run_is_incomplete(self, test_db):
        """Run abortado (finished_at nulo) → status 'incomplete' na leitura."""
        await start_run("abort1", "RTX 4060")
        # sem finish_run → finished_at nulo

        runs = await get_recent_runs()
        assert len(runs) == 1
        assert runs[0]["status"] == "incomplete"
        assert runs[0]["finished_at"] is None
        assert runs[0]["duration_ms"] is None

    @pytest.mark.asyncio
    async def test_get_recent_db_error_returns_empty(self):
        """Falha de leitura → ``[]`` com log (nunca lança)."""

        with patch("db.repositories.run_repo.get_db", _broken_get_db):
            assert await get_recent_runs() == []
