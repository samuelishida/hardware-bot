import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            window.chrome = { runtime: { id: 'xxx' } };
        """)

        page = await ctx.new_page()

        # Block unnecessary resources
        async def handle_route(route):
            if route.request.resource_type in ["image", "stylesheet", "font", "media"]:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", handle_route)

        await page.goto("https://lista.mercadolivre.com.br/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Try accepting cookies
        try:
            cookie_btn = await page.query_selector("button[data-testid='cookie-consent-banner-accept'], button:has-text('Aceitar cookies'), button.andes-button:has-text('Aceitar')")
            if cookie_btn:
                await cookie_btn.click()
                print("Clicked cookie consent")
                await page.wait_for_timeout(2000)
        except:
            print("No cookie consent found")

        # Check for login wall
        title = await page.title()
        print(f"Title: {title}")

        # Try clicking "Sou novo" or bypass login
        try:
            new_btn = await page.query_selector("button:has-text('Sou novo'), a:has-text('Sou novo')")
            if new_btn:
                await new_btn.click()
                print("Clicked 'Sou novo'")
                await page.wait_for_timeout(3000)
        except:
            pass

        for sel in ["li.ui-search-layout__item", "div.ui-search-result__content", "div.andes-card", "article"]:
            els = await page.query_selector_all(sel)
            print(f"{sel}: {len(els)}")

        text = await page.inner_text("body")
        lines = [l.strip() for l in text.split("\n") if l.strip()][:20]
        print("\nPage text:")
        for l in lines:
            print(f"  {l[:100]}")

        rl = [l.strip() for l in text.split("\n") if "R$" in l][:5]
        print(f"\nR$ lines: {len(rl)}")
        for l in rl:
            print(f"  {l[:100]}")

        await browser.close()

asyncio.run(main())