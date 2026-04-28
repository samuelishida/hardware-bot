"""Test the new KaBuM scraper."""
import asyncio, sys
from scrapers.kabum import KabumScraper, BaseScraper, ScrapeResult
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
        scraper = KabumScraper(browser=browser, search_term="rtx-4060")
        result = await scraper.scrape()
        print(f"Result: price={result.price}, available={result.available}, url={result.url}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())