"""tests/test_relevance_repo.py — Unit tests for db/repositories/relevance_repo.py (Inc 2).

Usa SQLite em memória (mesmo padrão de test_repositories.py).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import patch

from db.repositories.relevance_repo import get_terms, add_term, get_all_terms


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row

    await conn.execute("""
        CREATE TABLE relevance_overrides (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id   TEXT    NOT NULL,
            term       TEXT    NOT NULL,
            source     TEXT    NOT NULL DEFAULT 'llm',
            created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(store_id, term)
        )
    """)
    await conn.commit()

    @asynccontextmanager
    async def mock_get_db():
        yield conn

    with patch("db.repositories.relevance_repo.get_db", mock_get_db):
        yield conn

    await conn.close()


class TestRelevanceRepo:
    @pytest.mark.asyncio
    async def test_add_and_get_terms(self, test_db):
        await add_term("kabum", "ps link")
        await add_term("kabum", "Adaptador")  # normaliza para lowercase
        terms = await get_terms("kabum")
        assert terms == ["ps link", "adaptador"]

    @pytest.mark.asyncio
    async def test_add_term_normalizes_accent_and_whitespace(self, test_db):
        # NOTE 8 (audit): "Pasta Térmica" e "pasta termica" colapsam para o mesmo
        # termo (de-accent + collapse), então o UNIQUE deduplica.
        await add_term("kabum", "Pasta Térmica")
        await add_term("kabum", "pasta   termica")
        terms = await get_terms("kabum")
        assert terms == ["pasta termica"]

    @pytest.mark.asyncio
    async def test_add_term_idempotent(self, test_db):
        await add_term("kabum", "ps link")
        await add_term("kabum", "ps link")
        terms = await get_terms("kabum")
        assert terms == ["ps link"]

    @pytest.mark.asyncio
    async def test_add_term_empty_noop(self, test_db):
        await add_term("kabum", "   ")
        assert await get_terms("kabum") == []

    @pytest.mark.asyncio
    async def test_get_terms_scoped_by_store(self, test_db):
        await add_term("kabum", "ps link")
        await add_term("amazon", "cabo")
        assert await get_terms("kabum") == ["ps link"]
        assert await get_terms("amazon") == ["cabo"]

    @pytest.mark.asyncio
    async def test_get_all_terms(self, test_db):
        await add_term("kabum", "ps link")
        await add_term("amazon", "cabo")
        all_terms = await get_all_terms()
        assert len(all_terms) == 2
        assert {t["store_id"] for t in all_terms} == {"kabum", "amazon"}
        assert {t["term"] for t in all_terms} == {"ps link", "cabo"}
        assert all(t["source"] == "llm" for t in all_terms)

    @pytest.mark.asyncio
    async def test_db_error_degrades_to_empty(self, test_db):
        # tabela inexistente → get_terms degrada para [] (override é otimização)
        await test_db.execute("DROP TABLE relevance_overrides")
        await test_db.commit()
        assert await get_terms("kabum") == []
        assert await get_all_terms() == []