"""
db/repositories/price_repo.py — Price history repository.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from db.database import get_db

# Columns to SELECT — extracts JSON fields as named columns
_COLS = """
    id, store_id, product_name, price, available, scraped_at,
    json_extract(data, '$.search_term') AS search_term,
    json_extract(data, '$.stock_label') AS stock_label,
    json_extract(data, '$.url')         AS url
"""


@dataclass
class PriceRecord:
    store_id: str
    price: Optional[float]
    available: bool
    stock_label: Optional[str]
    url: Optional[str]
    scraped_at: str
    product_name: str = ""
    search_term: str = ""


def _to_record(r) -> PriceRecord:
    return PriceRecord(
        store_id=r["store_id"],
        price=r["price"],
        available=bool(r["available"]),
        stock_label=r["stock_label"],
        url=r["url"],
        scraped_at=r["scraped_at"],
        product_name=r["product_name"] or "",
        search_term=r["search_term"] or "",
    )


async def insert_price(
    store_id: str,
    price: Optional[float],
    available: bool,
    stock_label: Optional[str],
    url: Optional[str],
    product_name: str = "",
    search_term: str = "",
) -> None:
    async with get_db() as db:
        await db.execute(
            """INSERT INTO price_history (store_id, product_name, price, available, data)
               VALUES (?, ?, ?, ?, json_object('search_term', ?, 'stock_label', ?, 'url', ?))""",
            (store_id, product_name, price, int(available), search_term, stock_label, url),
        )
        await db.commit()


async def get_latest_by_store(store_id: str, product_name: str = None) -> Optional[PriceRecord]:
    async with get_db() as db:
        if product_name:
            rows = await db.execute_fetchall(
                f"SELECT {_COLS} FROM price_history"
                " WHERE store_id = ? AND product_name = ?"
                " ORDER BY scraped_at DESC LIMIT 1",
                (store_id, product_name),
            )
        else:
            rows = await db.execute_fetchall(
                f"SELECT {_COLS} FROM price_history"
                " WHERE store_id = ?"
                " ORDER BY scraped_at DESC LIMIT 1",
                (store_id,),
            )
        return _to_record(rows[0]) if rows else None


async def get_all_latest(product_name: str = None) -> list[PriceRecord]:
    async with get_db() as db:
        if product_name:
            rows = await db.execute_fetchall(
                f"""SELECT {_COLS} FROM price_history
                   WHERE product_name = ?
                     AND id IN (
                       SELECT MAX(id) FROM price_history WHERE product_name = ? GROUP BY store_id
                     )
                   ORDER BY price ASC NULLS LAST""",
                (product_name, product_name),
            )
        else:
            rows = await db.execute_fetchall(
                f"""SELECT {_COLS} FROM price_history
                   WHERE id IN (
                       SELECT MAX(id) FROM price_history GROUP BY store_id
                   )
                   ORDER BY price ASC NULLS LAST"""
            )
        return [_to_record(r) for r in rows]


async def get_price_history(store_id: str, days: int = 30, product_name: str = None) -> list[PriceRecord]:
    async with get_db() as db:
        if product_name:
            rows = await db.execute_fetchall(
                f"SELECT {_COLS} FROM price_history"
                " WHERE store_id = ? AND product_name = ?"
                "   AND scraped_at >= datetime('now', ?, 'localtime')"
                " ORDER BY scraped_at ASC",
                (store_id, product_name, f"-{days} days"),
            )
        else:
            rows = await db.execute_fetchall(
                f"SELECT {_COLS} FROM price_history"
                " WHERE store_id = ?"
                "   AND scraped_at >= datetime('now', ?, 'localtime')"
                " ORDER BY scraped_at ASC",
                (store_id, f"-{days} days"),
            )
        return [_to_record(r) for r in rows]


async def get_history_stats(store_id: str, days: int = 30, product_name: str = None) -> Optional[dict]:
    """Return {min, max, avg, count} computed in SQL, not Python."""
    async with get_db() as db:
        sql = """
            SELECT MIN(price) AS min, MAX(price) AS max, AVG(price) AS avg, COUNT(*) AS n
            FROM price_history
            WHERE store_id = ? AND price IS NOT NULL
              AND scraped_at >= datetime('now', ?, 'localtime')
        """
        params = [store_id, f"-{days} days"]
        if product_name:
            sql += " AND product_name = ?"
            params.append(product_name)
        rows = await db.execute_fetchall(sql, params)
        r = rows[0]
        return {"min": r["min"], "max": r["max"], "avg": r["avg"], "n": r["n"]} if r["n"] else None


async def clear_price_cache(product_name: str = None) -> int:
    """Delete price_history rows. Scoped to product_name if given, else all rows."""
    async with get_db() as db:
        if product_name:
            cursor = await db.execute(
                "DELETE FROM price_history WHERE product_name = ?", (product_name,)
            )
        else:
            cursor = await db.execute("DELETE FROM price_history")
        await db.commit()
        return cursor.rowcount


async def get_historical_min(days: int = 30, product_name: str = None) -> Optional[PriceRecord]:
    async with get_db() as db:
        if product_name:
            rows = await db.execute_fetchall(
                f"SELECT {_COLS} FROM price_history"
                " WHERE product_name = ? AND price IS NOT NULL"
                "   AND scraped_at >= datetime('now', ?, 'localtime')"
                " ORDER BY price ASC LIMIT 1",
                (product_name, f"-{days} days"),
            )
        else:
            rows = await db.execute_fetchall(
                f"SELECT {_COLS} FROM price_history"
                " WHERE price IS NOT NULL"
                "   AND scraped_at >= datetime('now', ?, 'localtime')"
                " ORDER BY price ASC LIMIT 1",
                (f"-{days} days",),
            )
        return _to_record(rows[0]) if rows else None
