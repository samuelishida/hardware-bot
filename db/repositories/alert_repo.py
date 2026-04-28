"""
db/repositories/alert_repo.py — User alerts repository.

Handles all database operations related to user price alerts.
"""

from __future__ import annotations
from db.database import get_db
from config import DEFAULT_PRODUCT, DEFAULT_SEARCH_TERM


async def get_active_alerts() -> list[dict]:
    """Get all active user alerts."""
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM user_alerts WHERE active = 1"
        )
        return [dict(r) for r in rows]


async def deactivate_alert(discord_user_id: str) -> None:
    """Deactivate a user's alert."""
    async with get_db() as db:
        await db.execute(
            "UPDATE user_alerts SET active = 0 WHERE discord_user = ?",
            (discord_user_id,),
        )
        await db.commit()


async def set_user_alert(
    discord_user_id: str,
    target_price: float,
    product_name: str = DEFAULT_PRODUCT,
    search_term: str = DEFAULT_SEARCH_TERM,
) -> None:
    """Set or update a user's price alert."""
    async with get_db() as db:
        # Deactivate existing alert for same user + product
        await db.execute(
            "UPDATE user_alerts SET active = 0 WHERE discord_user = ? AND product_name = ?",
            (discord_user_id, product_name),
        )
        # Insert new alert
        await db.execute(
            "INSERT INTO user_alerts (discord_user, product_name, search_term, target_price) VALUES (?, ?, ?, ?)",
            (discord_user_id, product_name, search_term, target_price),
        )
        await db.commit()


async def cancel_user_alert(discord_user_id: str, product_name: str = None) -> None:
    """Cancel a user's alert. If product_name is None, cancel all alerts for user."""
    async with get_db() as db:
        if product_name:
            await db.execute(
                "UPDATE user_alerts SET active = 0 WHERE discord_user = ? AND product_name = ?",
                (discord_user_id, product_name),
            )
        else:
            await db.execute(
                "UPDATE user_alerts SET active = 0 WHERE discord_user = ?",
                (discord_user_id,),
            )
        await db.commit()


async def get_user_alert(discord_user_id: str, product_name: str = None) -> dict | None:
    """Get a user's active alert. If product_name is None, get any active alert."""
    async with get_db() as db:
        if product_name:
            rows = await db.execute_fetchall(
                "SELECT * FROM user_alerts WHERE discord_user = ? AND product_name = ? AND active = 1",
                (discord_user_id, product_name),
            )
        else:
            rows = await db.execute_fetchall(
                "SELECT * FROM user_alerts WHERE discord_user = ? AND active = 1",
                (discord_user_id,),
            )
        if not rows:
            return None
        return dict(rows[0])
