"""Quick: check KaBuM with stealth script via scraper's _new_page."""
import asyncio, sys
sys.path.insert(0, "/home/ubuntu/precosbot")
from playwright.async_api import async_playwright
from scrapers.kabum import KabumScraper

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"])
        scraper = KabumScraper(browser=browser, search_term="rtx-4060")
        page = await scraper._new_page()
        await page.goto("https://www.kabum.com.br/busca/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(12000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3000)

        result = await page.evaluate("""() => ({
            mains: document.querySelectorAll('main').length,
            mainsSc: document.querySelectorAll("main[class*='sc-']").length,
            links: document.querySelectorAll("a[href*='/produto/']").length,
            title: document.title?.substring(0, 50),
        })""")
        print(f"Result: {result}")
        await page.context().close()
        await browser.close()

asyncio.run(main())