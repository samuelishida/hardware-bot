"""
scheduler/executor.py — Scraper execution engine.

Handles running scrapers in parallel with proper browser lifecycle management.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Callable

from playwright.async_api import async_playwright, Browser
from scrapers.base import ScrapeResult

logger = logging.getLogger(__name__)

# Extra Chromium args for stealth + low memory
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


async def run_scraper(scraper_factory: Callable) -> ScrapeResult | None:
    """Execute a single scraper and return the result."""
    try:
        scraper = scraper_factory()
        async with scraper:
            return await scraper.scrape()
    except Exception as e:
        logger.error(f"[scraper] Falha: {e}", exc_info=True)
        return None


async def execute_browser_scrapers(
    browser: Browser,
    scraper_classes: list,
    search_term: str,
) -> list[ScrapeResult | None]:
    """Execute multiple browser-based scrapers in parallel."""
    tasks = [
        run_scraper(lambda cls=cls, b=browser, s=search_term: cls(browser=b, search_term=s))
        for cls in scraper_classes
    ]
    return list(await asyncio.gather(*tasks))


async def execute_http_scrapers(
    scraper_classes: list,
    search_term: str,
) -> list[ScrapeResult | None]:
    """Execute multiple HTTP-based scrapers in parallel."""
    tasks = [
        run_scraper(lambda cls=cls, s=search_term: cls(search_term=s))
        for cls in scraper_classes
    ]
    return list(await asyncio.gather(*tasks))


async def scrape_product(
    browser_scraper_classes: list,
    http_scraper_classes: list,
    search_term: str,
) -> list[ScrapeResult]:
    """Execute all scrapers for a single product."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=STEALTH_ARGS,
        )

        browser_results = await execute_browser_scrapers(browser, browser_scraper_classes, search_term)
        http_results = await execute_http_scrapers(http_scraper_classes, search_term)

        await browser.close()

        all_results = browser_results + http_results
        return [r for r in all_results if r is not None]