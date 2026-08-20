"""
tests/test_selector_repo.py — Unit tests for db/repositories/selector_repo.py (Inc 6).

In-memory SQLite (mesmo padrão de test_repositories.py): patch de
``db.repositories.selector_repo.get_db`` com um asynccontextmanager que
yielda a conexão.
"""

from __future__ import annotations

import aiosqlite
import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import patch

from db.repositories.selector_repo import (
    get_override,
    upsert_override,
    record_outcome,
    invalidate_if_unreliable,
    get_all_overrides,
)


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """In-memory DB com a tabela ``selector_overrides``, patched no repo."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row

    await conn.execute(
        """
        CREATE TABLE selector_overrides (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id      TEXT    NOT NULL,
            element       TEXT    NOT NULL,
            selector      TEXT    NOT NULL,
            source        TEXT    NOT NULL DEFAULT 'self_healing',
            validated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(store_id, element)
        )
        """
    )
    await conn.commit()

    @asynccontextmanager
    async def mock_get_db():
        yield conn

    with patch("db.repositories.selector_repo.get_db", mock_get_db):
        yield conn

    await conn.close()


class TestUpsertAndGet:
    @pytest.mark.asyncio
    async def test_upsert_then_get(self, test_db):
        await upsert_override("kabum", "price", "span.price-box")
        row = await get_override("kabum", "price")
        assert row is not None
        assert row["store_id"] == "kabum"
        assert row["element"] == "price"
        assert row["selector"] == "span.price-box"
        assert row["source"] == "self_healing"
        assert row["success_count"] == 0
        assert row["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, test_db):
        assert await get_override("kabum", "price") is None

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_and_resets_counts(self, test_db):
        await upsert_override("kabum", "price", "span.old")
        await record_outcome("kabum", "price", True)
        await record_outcome("kabum", "price", False)

        await upsert_override("kabum", "price", "span.new")
        row = await get_override("kabum", "price")
        assert row["selector"] == "span.new"
        # contadores resetados no upsert
        assert row["success_count"] == 0
        assert row["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_upsert_is_per_store_element(self, test_db):
        await upsert_override("kabum", "price", "span.kabum")
        await upsert_override("pichau", "price", "span.pichau")
        assert (await get_override("kabum", "price"))["selector"] == "span.kabum"
        assert (await get_override("pichau", "price"))["selector"] == "span.pichau"


class TestRecordOutcome:
    @pytest.mark.asyncio
    async def test_record_success_and_failure(self, test_db):
        await upsert_override("kabum", "price", "span.price")
        await record_outcome("kabum", "price", True)
        await record_outcome("kabum", "price", True)
        await record_outcome("kabum", "price", False)

        row = await get_override("kabum", "price")
        assert row["success_count"] == 2
        assert row["failure_count"] == 1

    @pytest.mark.asyncio
    async def test_record_outcome_without_override_is_noop(self, test_db):
        # não deve lançar nem criar linha
        await record_outcome("kabum", "price", True)
        assert await get_override("kabum", "price") is None


class TestInvalidate:
    @pytest.mark.asyncio
    async def test_invalidated_when_failures_exceed_successes_by_grace(self, test_db):
        await upsert_override("kabum", "price", "span.price")
        # override recém-persistido (0 acertos); 2 falhas > 0 + 1 (carência) → remove
        await record_outcome("kabum", "price", False)
        await record_outcome("kabum", "price", False)

        removed = await invalidate_if_unreliable("kabum", "price")
        assert removed is True
        assert await get_override("kabum", "price") is None

    @pytest.mark.asyncio
    async def test_single_failure_on_fresh_override_is_kept(self, test_db):
        # carência de graça: 1 falha em override com 0 acertos não o elimina
        await upsert_override("kabum", "price", "span.price")
        await record_outcome("kabum", "price", False)

        removed = await invalidate_if_unreliable("kabum", "price")
        assert removed is False
        assert await get_override("kabum", "price") is not None

    @pytest.mark.asyncio
    async def test_kept_when_successes_ge_failures(self, test_db):
        await upsert_override("kabum", "price", "span.price")
        await record_outcome("kabum", "price", True)
        await record_outcome("kabum", "price", False)  # 1 == 1 → mantém

        removed = await invalidate_if_unreliable("kabum", "price")
        assert removed is False
        assert await get_override("kabum", "price") is not None

    @pytest.mark.asyncio
    async def test_invalidate_missing_returns_false(self, test_db):
        assert await invalidate_if_unreliable("kabum", "price") is False


class TestGetAll:
    @pytest.mark.asyncio
    async def test_get_all_overrides(self, test_db):
        await upsert_override("pichau", "price", "span.p")
        await upsert_override("kabum", "price", "span.k")
        rows = await get_all_overrides()
        assert {r["store_id"] for r in rows} == {"kabum", "pichau"}
        # ordenado por store_id, element
        assert [r["store_id"] for r in rows] == ["kabum", "pichau"]

    @pytest.mark.asyncio
    async def test_get_all_empty(self, test_db):
        assert await get_all_overrides() == []
