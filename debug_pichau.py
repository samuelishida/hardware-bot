"""Debug Pichau page structure."""
import asyncio, sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )
        page = await ctx.new_page()

        try:
            await page.goto("https://www.pichau.com.br/search?q=rtx-4060", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"Page load error: {e}", file=sys.stderr)
            await browser.close()
            return

        # Wait for JS rendering
        for i in range(15):
            await page.wait_for_timeout(2000)
            links = await page.query_selector_all("a[href*='/p/']")
            divs = await page.query_selector_all("div[class*=product], div[class*=Product]")
            if links or divs:
                print(f"Iteration {i}: links={len(links)}, divs={len(divs)}")
                break
            print(f"Iteration {i}: still waiting...")

        # Try various selectors
        for sel in ["a[href*='/p/']", "a[href*='/produto/']", "div[class*=product]", "div[class*=Product]", 
                     "span[class*=price]", "span[class*=Price]", "p[class*=price]", "p[class*=Price]",
                     "[data-product]", "a[href*='pichau']"]:
            els = await page.query_selector_all(sel)
            print(f"  {sel}: {len(els)}")

        # Get page text with prices
        text = await page.inner_text("body")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        plines = [l for l in lines if "R$" in l or "4060" in l.lower()]
        print(f"Lines with price/product ({len(plines)}):")
        for l in plines[:15]:
            print(f"  {l[:120]}")
        
        # Also check __NEXT_DATA__
        nd = await page.evaluate("() => { try { return document.getElementById('__NEXT_DATA__')?.textContent?.substring(0, 1000) } catch(e) { return null } }")
        if nd:
            print(f"__NEXT_DATA__ found ({len(nd)} chars):")
            print(nd[:500])
        
        await browser.close()

asyncio.run(main())