import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
        )
        page = await ctx.new_page()
        await page.goto("https://lista.mercadolivre.com.br/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)

        for sel in ["li.ui-search-layout__item", "div.ui-search-result__content", "div.andes-card", "article", "div.poly-card", "section.ui-search-layout"]:
            els = await page.query_selector_all(sel)
            print(f"{sel}: {len(els)}")

        text = await page.inner_text("body")
        lines = [l.strip() for l in text.split("\n") if l.strip()][:30]
        print("\nPage text:")
        for l in lines:
            print(f"  {l[:100]}")

        rl = [l.strip() for l in text.split("\n") if "R$" in l or "4060" in l.lower()][:10]
        print(f"\nR$/4060 lines: {len(rl)}")
        for l in rl:
            print(f"  {l[:100]}")

        await browser.close()

asyncio.run(main())