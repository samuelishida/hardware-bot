from __future__ import annotations
import logging
import random
import asyncio
import re
from .base import BaseScraper, ScrapeResult

logger = logging.getLogger(__name__)

EXTRA_STEALTH = """
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris Xe Graphics';
    return originalGetParameter.call(this, parameter);
};
"""


class EnjoeiScraper(BaseScraper):
    """Enjoei scraper for used products.

    Enjoei.com.br is a C2C marketplace focused on second-hand goods.
    It serves SSR HTML with product cards, no heavy SPA.
    """
    store_id = "enjoei"
    BASE_URL = "https://www.enjoei.com.br"

    def __init__(self, browser=None, search_term: str = None):
        super().__init__(browser)
        self.search_term = search_term

    def _build_search_url(self) -> str:
        term = re.sub(r'[^\w\s]', ' ', self.search_term).strip()
        q = '%20'.join(term.split())
        return f"{self.BASE_URL}/busca?term={q}"

    async def scrape(self) -> ScrapeResult:
        await asyncio.sleep(random.uniform(1.0, 3.0))
        return await self._browser_attempt()

    async def _browser_attempt(self) -> ScrapeResult:
        if self.browser is None:
            return ScrapeResult(self.store_id, None, False,
                                "Sem browser", self._build_search_url())

        ua = random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        ])
        vp = {"width": 1920, "height": 1080}

        page = None
        context = None
        try:
            context = await self.browser.new_context(
                user_agent=ua,
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport=vp,
                device_scale_factor=1,
                color_scheme="light",
            )
            from .base import STEALTH_SCRIPT
            await context.add_init_script(STEALTH_SCRIPT)
            await context.add_init_script(EXTRA_STEALTH)

            page = await context.new_page()
            await page.set_extra_http_headers({
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            })

            url = self._build_search_url()
            logger.info(f"[enjoei] Navegando: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
            except Exception:
                await page.goto(url, wait_until="commit", timeout=25_000)

            await page.wait_for_timeout(random.randint(2000, 4000))

            # Enjoei product cards are SSR — scrape DOM directly
            offers = await page.evaluate(r"""(keywords) => {
                const kws = keywords.replace(/-/g, ' ').toLowerCase().split(' ').filter(Boolean);
                const sig = kws.filter(k => k.length >= 2);
                const match = sig.length > 0 ? sig : kws;
                const model = kws.filter(k => /[0-9]/.test(k));

                // Enjoei cards are typically <article> or <div> with data-testid
                const cards = document.querySelectorAll('[data-testid="product-card"], [data-testid="offer-list-item"], article a[href^="/p/"], .css-product-card');
                const results = [];
                for (const card of cards) {
                    const titleEl = card.querySelector('h2, h3, [data-testid="product-title"], .css-product-title, a[href] h3');
                    const priceEl = card.querySelector('[data-testid="product-price"], .css-product-price, span:contains("R$")');
                    const linkEl = card.querySelector('a[href]');

                    let title = titleEl ? titleEl.innerText.trim() : '';
                    if (!title && linkEl) title = linkEl.innerText.trim();
                    if (!title) continue;
                    const titleL = title.toLowerCase();

                    if (model.length > 0 && !model.every(k => titleL.includes(k))) continue;
                    if (match.length > 0 && !match.every(k => titleL.includes(k))) continue;

                    let price = null;
                    // Search entire card text for price
                    const m = card.innerText.match(/R\$\s*([\d.,]+)/);
                    if (m) {
                        const raw = m[1].replace(/\./g, '').replace(',', '.');
                        const v = parseFloat(raw);
                        if (!isNaN(v) && v > 50) price = v;
                    }

                    const href = linkEl ? linkEl.href : null;
                    results.push({ title, price, url: href });
                }
                results.sort((a, b) => (a.price || Infinity) - (b.price || Infinity));
                return results;
            }""", self.search_term)

            if offers and len(offers) > 0:
                logger.info(f"[enjoei] {len(offers)} oferta(s) via DOM.")
                return self._pick_best(offers, url)

            return ScrapeResult(self.store_id, None, False,
                                "Não encontrado", url)

        except Exception as e:
            logger.warning(f"[enjoei] Falha: {e}")
            return ScrapeResult(self.store_id, None, False,
                                "Erro", self._build_search_url())
        finally:
            if context:
                await context.close()

    def _pick_best(self, offers: list[dict], fallback_url: str) -> ScrapeResult:
        valid = [o for o in offers if o.get('price') and o['price'] > 50]
        if not valid:
            if offers:
                return ScrapeResult(self.store_id, None, False,
                                    "Esgotado / Sem preço", fallback_url)
            return ScrapeResult(self.store_id, None, False,
                                "Não encontrado", fallback_url)
        valid.sort(key=lambda x: x['price'])
        best = valid[0]
        return ScrapeResult(
            self.store_id,
            best['price'],
            True,
            "Em estoque",
            best.get('url') or fallback_url,
        )
