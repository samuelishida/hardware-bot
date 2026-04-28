from __future__ import annotations
import logging
import asyncio
import random
from .base import BaseScraper, ScrapeResult, STEALTH_SCRIPT, USER_AGENTS, VIEWPORTS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.terabyteshop.com.br"


class TeraScraper(BaseScraper):
    store_id = "terabyte"

    def __init__(self, browser=None, search_term: str = None):
        super().__init__(browser)
        self.search_term = search_term
        self.search_url = f"https://www.terabyteshop.com.br/busca?str={self.search_term}"

    async def scrape(self) -> ScrapeResult:
        await asyncio.sleep(random.uniform(2.0, 5.0))
        result = await self._browser_attempt()
        if result is not None:
            return result
        logger.warning("[terabyte] Tentativa 1 falhou, tentando novamente...")
        await asyncio.sleep(random.uniform(2.0, 4.0))
        result = await self._browser_attempt()
        if result is not None:
            return result
        return ScrapeResult(self.store_id, None, False, "Erro", self.search_url)

    async def _browser_attempt(self) -> ScrapeResult | None:
        from playwright.async_api import async_playwright

        ua = random.choice(USER_AGENTS)
        vp = random.choice(VIEWPORTS)
        pw = None
        browser = None
        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--window-size=1920,1080",
                ],
            )

            context = await browser.new_context(
                user_agent=ua,
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport=vp,
                device_scale_factor=1,
                color_scheme="light",
                reduced_motion="no-preference",
                extra_http_headers={
                    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                    "Sec-CH-UA-Mobile": "?0",
                    "Sec-CH-UA-Platform": '"Windows"',
                },
            )

            await context.add_init_script(STEALTH_SCRIPT)

            page = await context.new_page()

            await page.goto(self.search_url, wait_until="commit", timeout=60_000)

            # Handle Cloudflare challenge
            for attempt in range(3):
                title = await page.title()
                if "just a moment" in title.lower() or "cloudflare" in title.lower():
                    logger.warning(f"[terabyte] Cloudflare challenge (attempt {attempt + 1}), waiting...")
                    await page.wait_for_timeout(random.randint(8000, 15000))
                else:
                    break
            else:
                logger.warning("[terabyte] Cloudflare challenge not solved after 3 waits.")
                return None

            # Wait for initial server-rendered products to appear (before
            # the "Tera Smart Search" JS replaces them with SPA results).
            # Must extract ASAP — the SPA overwrites the DOM within ~8s.
            try:
                await page.wait_for_selector(
                    "div.product-item", timeout=20_000
                )
                logger.info("[terabyte] Initial product cards loaded.")
            except Exception:
                logger.warning("[terabyte] Product cards did not load.")
                return None

            # Evaluate immediately — no extra wait, or the SPA will replace products
            products = await page.evaluate(
                """(searchTerm) => {
                const keywords = searchTerm.replace(/-/g, ' ').toLowerCase().split(' ');
                const modelKws = keywords.filter(kw => /[0-9]/.test(kw));

                const items = document.querySelectorAll('div.product-item');
                const results = [];

                for (const item of items) {
                    const nameEl = item.querySelector('a.product-item__name');
                    if (!nameEl) continue;

                    const name = nameEl.innerText.trim();
                    const url = nameEl.href;
                    const nameLower = name.toLowerCase();

                    if (!modelKws.every(kw => nameLower.includes(kw))) continue;
                    if (!keywords.some(kw => nameLower.includes(kw))) continue;

                    const newPriceEl = item.querySelector('div.product-item__new-price');
                    const priceText = newPriceEl ? newPriceEl.innerText.trim() : '';

                    let price = null;
                    const m = priceText.match(/R\\$\\s*([\\d.,]+)/);
                    if (m) {
                        const raw = m[1].replace(/\\./g, '').replace(',', '.');
                        const val = parseFloat(raw);
                        if (!isNaN(val) && val > 10) price = val;
                    }

                    const itemText = item.innerText.toLowerCase();
                    const available = price !== null
                        && !itemText.includes('indisponível')
                        && !itemText.includes('indisponivel')
                        && !itemText.includes('esgotado')
                        && !itemText.includes('sem estoque');

                    const matchCount = keywords.filter(kw => nameLower.includes(kw)).length;
                    results.push({ price, available, url, name: name.substring(0, 200), matchCount });
                }

                results.sort((a, b) => b.matchCount - a.matchCount || a.price - b.price);
                return results;
            }""",
                self.search_term,
            )

            if not products:
                logger.info("[terabyte] Nenhum produto encontrado na página.")
                return None

            # Results sorted by relevance then price — pick first available
            for p in products:
                if p["available"] and p["price"] is not None:
                    return ScrapeResult(self.store_id, p["price"], True, "Em estoque", p["url"])

            p = products[0]
            return ScrapeResult(self.store_id, p["price"], p["available"],
                                "Em estoque" if p["available"] else "Esgotado", p["url"])

        except Exception as e:
            logger.error(f"[terabyte] Browser attempt falhou: {e}")
            return None
        finally:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()

