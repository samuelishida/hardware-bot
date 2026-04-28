"""Debug KaBuM — dump grandparent div contents of product links."""
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

        await page.goto("https://www.kabum.com.br/busca/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)

        # Get all product card containers and their text
        cards_data = await page.evaluate("""() => {
            let links = document.querySelectorAll("a[href*='/produto/']");
            let results = [];
            for (let i = 0; i < Math.min(links.length, 8); i++) {
                let card = links[i].closest('div[class]')?.parentElement || links[i].parentElement?.parentElement;
                if (!card) continue;
                let text = card.innerText.trim().substring(0, 200);
                let html = card.innerHTML.substring(0, 500);
                results.push({text, htmlSnippet: html});
            }
            return results;
        }""")

        for i, c in enumerate(cards_data):
            print(f"\n--- Card {i} ---")
            print(f"TEXT: {c['text'][:150]}")
            print(f"HTML: {c['htmlSnippet'][:200]}")

        await browser.close()

asyncio.run(main())