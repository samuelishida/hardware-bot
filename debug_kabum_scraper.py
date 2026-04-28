"""Quick debug — check KaBuM page loading in current state."""
import asyncio
import sys
sys.path.insert(0, "/home/ubuntu/precosbot")

from playwright.async_api import async_playwright

STEALTH_ARGS = [
    "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--window-size=1920,1080",
]

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            ]});
            Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
        """)
        page = await ctx.new_page()

        try:
            resp = await page.goto("https://www.kabum.com.br/busca/rtx-4060", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(12000)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)

            print(f"Status: {resp.status if resp else 'N/A'}")
            title = await page.title()
            print(f"Title: {title}")

            mains = await page.evaluate('() => document.querySelectorAll("main").length')
            print(f"<main> elements: {mains}")

            product_links = await page.evaluate('() => document.querySelectorAll(\'a[href*="/produto/"]\').length')
            print(f'Product links: {product_links}')

            # Try the scraper's evaluate
            from scrapers.kabum import KabumScraper
            scraper = KabumScraper(browser=browser, search_term="rtx-4060")
            scraper_page = await scraper._new_page()
            await scraper_page.goto(scraper.search_url, wait_until="commit", timeout=30000)
            await scraper_page.wait_for_timeout(12000)
            await scraper_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await scraper_page.wait_for_timeout(3000)

            result = await scraper_page.evaluate("""(searchTerm) => {
                const keywords = searchTerm.replace(/-/g, ' ').split(' ');
                const mainCards = document.querySelectorAll("main[class*='sc-']");
                const allMains = document.querySelectorAll("main");
                const productLinks = document.querySelectorAll("a[href*='/produto/']");
                return {
                    mainCards: mainCards.length,
                    allMains: allMains.length,
                    productLinks: productLinks.length,
                    bodyText: document.body.innerText.substring(0, 300),
                };
            }""", "rtx-4060")
            print(f"Scraper evaluate: {result}")

            await scraper_page.close()
        except Exception as e:
            print(f"Error: {e}")

        await browser.close()

asyncio.run(main())