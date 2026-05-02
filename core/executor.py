"""
core/executor.py — Scraper execution engine.

Runs all scrapers sequentially sharing one browser instance (1 GB RAM constraint).
"""

from __future__ import annotations
import asyncio
import logging

from playwright.async_api import async_playwright
from scrapers.base import ScrapeResult

logger = logging.getLogger(__name__)

SCRAPER_TIMEOUT = 90

STEALTH_ARGS = [
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-default-apps",
    "--disable-hang-monitor",
    "--disable-popup-blocking",
    "--disable-renderer-backgrounding",
    "--disable-blink-features=AutomationControlled",
    "--window-size=1920,1080",
]


async def scrape_product(
    browser_scraper_classes: list,
    http_scraper_classes: list,
    search_term: str,
) -> list[ScrapeResult]:
    """Execute all scrapers sequentially sharing one browser."""
    all_classes = browser_scraper_classes + http_scraper_classes
    results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)

        for cls in all_classes:
            store_id = getattr(cls, 'store_id', cls.__name__)
            try:
                scraper = cls(browser=browser, search_term=search_term)
                async with scraper:
                    result = await asyncio.wait_for(
                        scraper.scrape(), timeout=SCRAPER_TIMEOUT
                    )
            except asyncio.TimeoutError:
                logger.warning(f"[{store_id}] Timeout após {SCRAPER_TIMEOUT}s — pulando.")
                result = None
            except Exception as e:
                logger.error(f"[{store_id}] Falha: {e}", exc_info=True)
                result = None

            if result is not None:
                results.append(result)

    return results
