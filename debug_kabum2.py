"""Debug KaBuM page structure — what surrounds product links."""
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
            await page.goto("https://www.kabum.com.br/busca/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"Page load error: {e}", file=sys.stderr)
            await browser.close()
            return

        # Wait for product links
        for i in range(10):
            await page.wait_for_timeout(2000)
            links = await page.query_selector_all("a[href*='/produto/']")
            if len(links) > 2:
                print(f"Iteration {i}: {len(links)} product links found")
                break
            print(f"Iteration {i}: {len(links)} links")

        # Examine first few product link containers
        links = await page.query_selector_all("a[href*='/produto/']")
        print(f"\nTotal product links: {len(links)}")
        
        for i, link in enumerate(links[:5]):
            href = await link.get_attribute("href")
            text = (await link.inner_text()).strip()[:100]
            # Get parent element's class
            parent_class = await link.evaluate("el => el.parentElement?.className || 'no-parent'")
            grandparent_class = await link.evaluate("el => el.parentElement?.parentElement?.className || 'no-gp'")
            print(f"\nLink {i}: {text}")
            print(f"  href: {href}")
            print(f"  parent class: {parent_class[:80]}")
            print(f"  grandparent class: {grandparent_class[:80]}")
            
            # Check for price nearby
            parent = await link.evaluate_handle("el => el.closest('div[class]') || el.parentElement")
            price_els = await link.evaluate("""el => {
                let container = el.closest('div') || el.parentElement;
                if (!container) return 'no-container';
                let prices = container.querySelectorAll('span[class*=price], span[class*=Price], [class*=price]');
                return Array.from(prices).map(p => ({class: p.className.substring(0, 60), text: p.textContent.trim().substring(0, 40)}));
            }""")
            print(f"  price elements: {price_els}")

        # Check for specific price selectors within product links
        for sel in ["span[class*=price]", "span[class*=Price]", "[class*=priceCard]", "[class*=nameCard]"]:
            els = await page.query_selector_all(sel)
            print(f"\n{sel}: {len(els)} elements")
            if els:
                for e in els[:2]:
                    txt = (await e.inner_text()).strip()[:60]
                    cls = await e.evaluate("el => el.className")
                    print(f"  class={cls[:60]} text={txt}")

        await browser.close()

asyncio.run(main())