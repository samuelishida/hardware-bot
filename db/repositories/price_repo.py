"""
db/repositories/price_repo.py — Price history repository.

Handles all database operations related to price records.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from db.database import get_db
from config import DEFAULT_PRODUCT, DEFAULT_SEARCH_TERM


def _row_value(row, key: str, default):
    keys = row.keys() if hasattr(row, "keys") else []
    return row[key] if key in keys else default


@dataclass
class PriceRecord:
    store_id: str
    price: Optional[float]
    available: bool
    stock_label: Optional[str]
    url: Optional[str]
    scraped_at: str
    product_name: str = DEFAULT_PRODUCT
    search_term: str = DEFAULT_SEARCH_TERM


async def insert_price(
    store_id: str,
    price: Optional[float],
    available: bool,
    stock_label: Optional[str],
    url: Optional[str],
    product_name: str = DEFAULT_PRODUCT,
    search_term: str = DEFAULT_SEARCH_TERM,
) -> None:
    """Insert a new price record into the database."""
    async with get_db() as db:
        await db.execute(
            """INSERT INTO price_history (store_id, product_name, search_term, price, available, stock_label, url)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (store_id, product_name, search_term, price, int(available), stock_label, url),
        )
        await db.commit()


async def get_latest_by_store(store_id: str, product_name: str = None) -> Optional[PriceRecord]:
    """Get the latest price record for a specific store."""
    async with get_db() as db:
        if product_name:
            rows = await db.execute_fetchall(
                """SELECT * FROM price_history
                   WHERE store_id = ? AND product_name = ?
                   ORDER BY scraped_at DESC LIMIT 1""",
                (store_id, product_name),
            )
        else:
            rows = await db.execute_fetchall(
                """SELECT * FROM price_history
                   WHERE store_id = ?
                   ORDER BY scraped_at DESC LIMIT 1""",
                (store_id,),
            )
        if not rows:
            return None
        r = rows[0]
        return PriceRecord(
            store_id=r["store_id"],
            price=r["price"],
            available=bool(r["available"]),
            stock_label=r["stock_label"],
            url=r["url"],
            scraped_at=r["scraped_at"],
            product_name=_row_value(r, "product_name", DEFAULT_PRODUCT),
            search_term=_row_value(r, "search_term", DEFAULT_SEARCH_TERM),
        )


async def get_all_latest(product_name: str = None) -> list[PriceRecord]:
    """Get the latest price record for each store."""
    async with get_db() as db:
        if product_name:
            rows = await db.execute_fetchall(
                """SELECT * FROM price_history
                   WHERE product_name = ?
                     AND id IN (
                       SELECT MAX(id) FROM price_history WHERE product_name = ? GROUP BY store_id
                     )
                   ORDER BY price ASC NULLS LAST""",
                (product_name, product_name),
            )
        else:
            rows = await db.execute_fetchall(
                """SELECT * FROM price_history
                   WHERE id IN (
                       SELECT MAX(id) FROM price_history GROUP BY store_id
                   )
                   ORDER BY price ASC NULLS LAST"""
            )
        return [
            PriceRecord(
                store_id=r["store_id"],
                price=r["price"],
                available=bool(r["available"]),
                stock_label=r["stock_label"],
                url=r["url"],
                scraped_at=r["scraped_at"],
                product_name=_row_value(r, "product_name", "AMD Ryzen 5 5700X3D"),
                search_term=_row_value(r, "search_term", "ryzen-5-5700x3d"),
            )
            for r in rows
        ]


async def get_price_history(store_id: str, days: int = 30, product_name: str = None) -> list[PriceRecord]:
    """Get price history for a store over the last N days."""
    async with get_db() as db:
        if product_name:
            rows = await db.execute_fetchall(
                """SELECT * FROM price_history
                   WHERE store_id = ? AND product_name = ?
                     AND scraped_at >= datetime('now', ?, 'localtime')
                   ORDER BY scraped_at ASC""",
                (store_id, product_name, f"-{days} days"),
            )
        else:
            rows = await db.execute_fetchall(
                """SELECT * FROM price_history
                   WHERE store_id = ?
                     AND scraped_at >= datetime('now', ?, 'localtime')
                   ORDER BY scraped_at ASC""",
                (store_id, f"-{days} days"),
            )
        return [
            PriceRecord(
                store_id=r["store_id"],
                price=r["price"],
                available=bool(r["available"]),
                stock_label=r["stock_label"],
                url=r["url"],
                scraped_at=r["scraped_at"],
                product_name=_row_value(r, "product_name", "AMD Ryzen 5 5700X3D"),
                search_term=_row_value(r, "search_term", "ryzen-5-5700x3d"),
            )
            for r in rows
        ]


async def get_historical_min(days: int = 30, product_name: str = None) -> Optional[PriceRecord]:
    """Get the lowest price recorded in the last N days."""
    async with get_db() as db:
        if product_name:
            rows = await db.execute_fetchall(
                """SELECT * FROM price_history
                   WHERE product_name = ? AND price IS NOT NULL
                     AND scraped_at >= datetime('now', ?, 'localtime')
                   ORDER BY price ASC LIMIT 1""",
                (product_name, f"-{days} days"),
            )
        else:
            rows = await db.execute_fetchall(
                """SELECT * FROM price_history
                   WHERE price IS NOT NULL
                     AND scraped_at >= datetime('now', ?, 'localtime')
                   ORDER BY price ASC LIMIT 1""",
                (f"-{days} days",),
            )
        if not rows:
            return None
        r = rows[0]
        return PriceRecord(
            store_id=r["store_id"],
            price=r["price"],
            available=bool(r["available"]),
            stock_label=r["stock_label"],
            url=r["url"],
            scraped_at=r["scraped_at"],
            product_name=_row_value(r, "product_name", DEFAULT_PRODUCT),
            search_term=_row_value(r, "search_term", DEFAULT_SEARCH_TERM),
        )
