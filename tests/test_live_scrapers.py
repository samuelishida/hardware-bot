"""
tests/test_live_scrapers.py — Live integration test for scrapers.

Runs each scraper against the real store, one at a time, with timeout.
Usage: python -m tests.test_live_scrapers [store]
  store: terabyte, pichau, kabum, amazon, all

Inc 4 (Lightpanda): usa a facade ``LightpandaBrowser`` (core/browser.py) em vez
de Playwright. Requer o binário ``lightpanda`` no PATH ou ``LIGHTPANDA_BIN``.
"""
from __future__ import annotations
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.browser import LightpandaBrowser
from scrapers.kabum import KabumScraper
from scrapers.pichau import PichauScraper
from scrapers.terabyte import TeraScraper
from scrapers.amazon import AmazonScraper

BROWSER_SCRAPERS = {
    "kabum": KabumScraper,
    "pichau": PichauScraper,
    "terabyte": TeraScraper,
    "amazon": AmazonScraper,
}

async def test_scraper(name: str, search_term: str = "rtx-4060") -> None:
    print(f"\n{'='*60}")
    print(f"  Testing: {name} with '{search_term}'")
    print(f"{'='*60}")

    start = time.time()
    try:
        if name in BROWSER_SCRAPERS:
            browser = LightpandaBrowser()
            await browser.start()
            scraper = BROWSER_SCRAPERS[name](browser=browser, search_term=search_term)
            result = await scraper.scrape()
            await browser.stop()
        else:
            print(f"  Unknown scraper: {name}")
            return
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    elapsed = time.time() - start
    print(f"  store_id:    {result.store_id}")
    print(f"  price:       {result.price}")
    print(f"  available:    {result.available}")
    print(f"  stock_label: {result.stock_label}")
    print(f"  url:         {result.url}")
    print(f"  elapsed:     {elapsed:.1f}s")

    if result.price is not None:
        print(f"  ✅ SUCCESS — got price R$ {result.price:,.2f}")
    else:
        print(f"  ❌ FAIL — no price returned")


async def main():
    stores = sys.argv[1:] if len(sys.argv) > 1 else ["all"]

    if "all" in stores:
        order = ["pichau", "kabum", "terabyte", "amazon"]
    else:
        order = [s for s in stores if s in BROWSER_SCRAPERS]

    for name in order:
        await test_scraper(name)
        print()
        await asyncio.sleep(2)  # Avoid hammering

if __name__ == "__main__":
    asyncio.run(main())