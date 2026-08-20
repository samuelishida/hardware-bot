"""
toolkit.py — PreçoBot agentic scraping toolkit.

Clean async Python API for hermes-agent and other consumers.
All functions are standalone — no Discord, no scheduler.
"""

from __future__ import annotations
from typing import Optional

from core.product_manager import ProductManager
from core.executor import scrape_product
from scrapers import BROWSER_SCRAPERS, HTTP_SCRAPERS
from scrapers.base import ScrapeResult
from db.repositories import (
    PriceRecord,
    insert_price,
    get_all_latest,
    get_price_history,
    get_history_stats,
    get_historical_min,
)
from config import STORE_URL_TEMPLATES
from utils.history_logger import log_scrape


async def scrape(product: str) -> list[ScrapeResult]:
    """Live scrape across all stores. Does not write to DB."""
    ps = ProductManager.parse_product_name(product)
    return await scrape_product(BROWSER_SCRAPERS, HTTP_SCRAPERS, ps.search_term)


async def scrape_and_store(product: str) -> list[ScrapeResult]:
    """Live scrape across all stores and persist results to DB + HISTORY.md."""
    ps = ProductManager.parse_product_name(product)
    results = await scrape_product(BROWSER_SCRAPERS, HTTP_SCRAPERS, ps.search_term)
    for r in results:
        await insert_price(
            store_id=r.store_id,
            price=r.price,
            available=r.available,
            stock_label=r.stock_label,
            url=r.url,
            product_name=ps.name,
            search_term=ps.search_term,
            title=r.title,
        )
        log_scrape(
            store_id=r.store_id,
            product=ps.name,
            price=r.price,
            available=r.available,
            url=r.url,
        )
    return results


async def get_latest(product: str) -> list[PriceRecord]:
    """Latest cached prices from DB, sorted cheapest first."""
    return await get_all_latest(product_name=product)


async def get_history(product: str, days: int = 7) -> list[PriceRecord]:
    """Price history from DB across all stores, sorted by time."""
    store_ids = list(STORE_URL_TEMPLATES.keys())
    all_records: list[PriceRecord] = []
    for store_id in store_ids:
        records = await get_price_history(store_id, days=days, product_name=product)
        all_records.extend(records)
    all_records.sort(key=lambda r: r.scraped_at)
    return all_records


async def best_deal(product: str, live: bool = False) -> Optional[PriceRecord]:
    """
    Cheapest available price. live=True triggers a fresh scrape first.
    Returns None if no prices found.
    """
    if live:
        await scrape_and_store(product)
    records = await get_all_latest(product_name=product)
    available = [r for r in records if r.available and r.price is not None]
    return min(available, key=lambda r: r.price) if available else None


async def compare(products: list[str]) -> dict[str, list[PriceRecord]]:
    """Latest cached prices for multiple products keyed by product name."""
    # Sequential intentional — SQLite serializes writes anyway, no benefit to gather()
    return {p: await get_all_latest(product_name=p) for p in products}


async def get_analysis(product: str, days: int = 30) -> dict:
    """Price trend analysis: per-store min/max/avg + overall historical minimum."""
    store_ids = list(STORE_URL_TEMPLATES.keys())
    per_store: dict[str, dict] = {}
    for store_id in store_ids:
        stats = await get_history_stats(store_id, days=days, product_name=product)
        if stats and stats["n"]:
            per_store[store_id] = stats
    overall_min = await get_historical_min(days=days, product_name=product)
    return {
        "product": product,
        "days": days,
        "per_store": per_store,
        "overall_min": {
            "price": overall_min.price,
            "store_id": overall_min.store_id,
            "scraped_at": overall_min.scraped_at,
            "url": overall_min.url,
        } if overall_min else None,
    }
