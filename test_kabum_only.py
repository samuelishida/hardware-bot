import asyncio, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from playwright.async_api import async_playwright
from scrapers.kabum import KabumScraper
from scrapers.base import STEALTH_SCRIPT

STEALTH_ARGS = ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]

async def test_kabum():
    search = sys.argv[1] if len(sys.argv) > 1 else "rtx-4060"
    print(f"Testing KaBuM with '{search}'...")
    start = time.time()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
        scraper = KabumScraper(browser=browser, search_term=search)
        result = await scraper.scrape()
        await browser.close()
    elapsed = time.time() - start
    print(f"price={result.price} available={result.available} stock={result.stock_label}")
    print(f"url={result.url}")
    print(f"elapsed={elapsed:.1f}s")
    if result.price is not None:
        print("SUCCESS")
    else:
        print("FAIL")

asyncio.run(test_kabum())