import asyncio, json, sys
sys.path.insert(0, '.')
from scrapers.mercadolivre import COOKIE_FILE, _ML_EXTRA_STEALTH, _PERMISSIONS_SCRIPT, _SEC_CH_UA, _SEC_CH_UA_FULL
from scrapers.base import STEALTH_SCRIPT, USER_AGENTS, VIEWPORTS
import random

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage',
                  '--disable-blink-features=AutomationControlled', '--window-size=1920,1080']
        )
        ctx = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale='pt-BR', timezone_id='America/Sao_Paulo',
            viewport=random.choice(VIEWPORTS),
            extra_http_headers={
                'Sec-CH-UA': _SEC_CH_UA, 'Sec-CH-UA-Mobile': '?0', 'Sec-CH-UA-Platform': '"Windows"',
            },
        )
        await ctx.add_init_script(STEALTH_SCRIPT)
        await ctx.add_init_script(_ML_EXTRA_STEALTH)
        await ctx.add_init_script(_PERMISSIONS_SCRIPT)

        saved = json.loads(COOKIE_FILE.read_text()) if COOKIE_FILE.exists() else []
        if saved:
            await ctx.add_cookies(saved)

        page = await ctx.new_page()
        async def _route(route):
            if route.request.resource_type in ('image', 'media', 'font'):
                await route.abort()
            else:
                await route.continue_()
        await page.route('**/*', _route)

        await page.goto('https://lista.mercadolivre.com.br/rtx-4060-ti', wait_until='domcontentloaded', timeout=35000)
        await page.wait_for_timeout(4000)

        print('url:', page.url[:80])
        if 'account-verification' in page.url:
            print('STILL HIT LOGIN WALL')
            await browser.close()
            return

        # Dump first card's price elements
        result = await page.evaluate("""() => {
            const selectors = [
                'li.ui-search-layout__item',
                'div.poly-card',
                'div.andes-card',
                'article',
            ];
            let cards = [];
            for (const sel of selectors) {
                const found = document.querySelectorAll(sel);
                if (found.length >= 3) { cards = Array.from(found); break; }
            }
            if (!cards.length) return { error: 'no cards', selector_counts: Object.fromEntries(
                ['li.ui-search-layout__item','div.poly-card','div.andes-card','article'].map(s => [s, document.querySelectorAll(s).length])
            )};

            const card = cards[0];
            // Collect all elements with class containing price
            const priceEls = card.querySelectorAll('[class*=price], [class*=amount], [class*=money]');
            const priceInfo = [...priceEls].slice(0, 20).map(el => ({
                cls: el.className,
                text: el.innerText.trim().substring(0, 80),
            }));

            // Full card text
            const fullText = card.innerText.substring(0, 500);

            return { cardCount: cards.length, priceInfo, fullText };
        }""")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        await browser.close()

asyncio.run(main())
