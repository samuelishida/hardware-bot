"""
db/repositories/tracking_repo.py — Product tracking repository.

Handles all database operations related to channel product tracking.
"""

from __future__ import annotations
from db.database import get_db


async def get_tracked_products(channel_id: str) -> list[dict]:
    """Get all products being tracked in a specific channel."""
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM tracked_products WHERE channel_id = ? AND active = 1",
            (str(channel_id),)
        )
        return [dict(r) for r in rows]


async def add_tracked_product(channel_id: str, product_name: str, search_term: str) -> None:
    """Add a product to track in a channel."""
    async with get_db() as db:
        await db.execute(
            "INSERT INTO tracked_products (channel_id, product_name, search_term) VALUES (?, ?, ?)",
            (str(channel_id), product_name, search_term),
        )
        await db.commit()


async def remove_tracked_product(channel_id: str, product_name: str) -> None:
    """Remove a tracked product from a channel (soft delete)."""
    async with get_db() as db:
        await db.execute(
            "UPDATE tracked_products SET active = 0 WHERE channel_id = ? AND product_name = ?",
            (str(channel_id), product_name),
        )
        await db.commit()


async def get_all_tracked_products() -> list[dict]:
    """Get all active tracked products across all channels (for scheduler)."""
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM tracked_products WHERE active = 1"
        )
        return [dict(r) for r in rows]


async def is_product_tracked(channel_id: str, product_name: str) -> bool:
    """Check if a product is already being tracked in a channel."""
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT 1 FROM tracked_products WHERE channel_id = ? AND product_name = ? AND active = 1",
            (str(channel_id), product_name),
        )
        return len(rows) > 0


async def get_tracked_product(channel_id: str, product_name: str) -> dict | None:
    """Get a specific tracked product in a channel."""
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM tracked_products WHERE channel_id = ? AND product_name = ? AND active = 1",
            (str(channel_id), product_name),
        )
        if not rows:
            return None
        return dict(rows[0])
