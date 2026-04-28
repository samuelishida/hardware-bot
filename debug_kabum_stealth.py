"""Test: does stealth script break KaBuM?"""
import asyncio, sys
sys.path.insert(0, "/home/ubuntu/precosbot")
from playwright.async_api import async_playwright
from scrapers.base import STEALTH_SCRIPT

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"])

        # TEST 1: No stealth
        ctx1 = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
        )
        page1 = await ctx1.new_page()
        await page1.goto("https://www.kabum.com.br/busca/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        await page1.wait_for_timeout(12000)
        result1 = await page1.evaluate("""() => ({
            mains: document.querySelectorAll('main').length,
            productLinks: document.querySelectorAll("a[href*='/produto/']").length,
            title: document.title?.substring(0, 50),
        })""")
        print(f"WITHOUT stealth: {result1}")
        await ctx1.close()

        # TEST 2: WITH stealth
        ctx2 = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
        )
        await ctx2.add_init_script(STEALTH_SCRIPT)
        page2 = await ctx2.new_page()
        await page2.goto("https://www.kabum.com.br/busca/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        await page2.wait_for_timeout(12000)
        result2 = await page2.evaluate("""() => ({
            mains: document.querySelectorAll('main').length,
            productLinks: document.querySelectorAll("a[href*='/produto/']").length,
            title: document.title?.substring(0, 50),
        })""")
        print(f"WITH stealth:    {result2}")
        await ctx2.close()

        # TEST 3: With stealth using the scraper's _new_page method
        from scrapers.kabum import KabumScraper
        scraper = KabumScraper(browser=browser, search_term="rtx-4060")
        page3 = await scraper._new_page()
        await page3.goto("https://www.kabum.com.br/busca/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        await page3.wait_for_timeout(12000)
        result3 = await page3.evaluate("""() => ({
            mains: document.querySelectorAll('main').length,
            productLinks: document.querySelectorAll("a[href*='/produto/']").length,
            title: document.title?.substring(0, 50),
        })""")
        print(f"With _new_page:  {result3}")
        await page3.context().close()

        await browser.close()

asyncio.run(main())