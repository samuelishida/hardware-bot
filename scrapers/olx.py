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


class OLXScraper(BaseScraper):
    """OLX Brasil scraper for used products.

    Uses Playwright to load the Next.js SPA, extract __NEXT_DATA__ JSON
    or fallback to DOM scraping. OLX has strong anti-bot on OCI IPs —
    requires stealth + cookies when available.
    """
    store_id = "olx"
    BASE_URL = "https://www.olx.com.br"

    def __init__(self, browser=None, search_term: str = None):
        super().__init__(browser)
        self.search_term = search_term

    def _build_search_url(self) -> str:
        term = re.sub(r'[^\w\s]', ' ', self.search_term).strip()
        q = '%20'.join(term.split())
        return f"{self.BASE_URL}/brasil?q={q}&sf=1"

    async def scrape(self) -> ScrapeResult:
        await asyncio.sleep(random.uniform(2.0, 4.0))
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
            logger.info(f"[olx] Navegando: {url}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=25_000)
            except Exception:
                await page.goto(url, wait_until="commit", timeout=25_000)

            await page.wait_for_timeout(random.randint(3000, 5000))

            # 1) Try __NEXT_DATA__ extraction first (the JSON is always fully
            #    populated once the SPA rehydrates, even if OCI anti-bot hides cards)
            raw = await page.evaluate("""
                () => {
                    const el = document.getElementById('__NEXT_DATA__');
                    return el ? el.innerText : null;
                }
            """)
            if raw:
                try:
                    data = __import__('json').loads(raw)
                    offers = self._extract_from_next_data(data)
                    if offers:
                        logger.info(f"[olx] {len(offers)} oferta(s) via __NEXT_DATA__.")
                        return self._pick_best(offers, url)
                except Exception:
                    pass

            # 2) Fallback to DOM scraping
            offers = await page.evaluate("""(keywords) => {
                const kws = keywords.replace(/-/g, ' ').toLowerCase().split(' ').filter(Boolean);
                const sig = kws.filter(k => k.length >= 2);
                const match = sig.length > 0 ? sig : kws;
                const model = kws.filter(k => /[0-9]/.test(k));

                const cards = document.querySelectorAll('[data-testid="listing-wrapper"], [data-testid="ad-card"], article, .olx-ad-card');
                const results = [];
                for (const card of cards) {
                    const titleEl = card.querySelector('a[href] > h2, a[data-testid="ad-card-title"], h3, .olx-ad-card__title, a[href] h3');
                    const priceEl = card.querySelector('[data-testid="ad-card-price"], .olx-ad-card__price, h3 + div, h3 ~ div');
                    const linkEl = card.querySelector('a[href]');

                    if (!titleEl) continue;
                    const title = titleEl.innerText.trim();
                    const titleL = title.toLowerCase();

                    if (model.length > 0 && !model.every(k => titleL.includes(k))) continue;
                    if (match.length > 0 && !match.every(k => titleL.includes(k))) continue;

                    let price = null;
                    if (priceEl) {
                        const m = priceEl.innerText.match(/R\\$\\s*([\\d.,]+)/);
                        if (m) {
                            const raw = m[1].replace(/\\./g,'').replace(',','.');
                            const v = parseFloat(raw);
                            if (!isNaN(v) && v > 100) price = v;
                        }
                    }

                    const href = linkEl ? linkEl.href : null;
                    results.push({ title, price, url: href });
                }
                results.sort((a,b) => (a.price||Infinity) - (b.price||Infinity));
                return results;
            }""", self.search_term)

            if offers:
                logger.info(f"[olx] {len(offers)} oferta(s) via DOM.")
                return self._pick_best(offers, url)

            return ScrapeResult(self.store_id, None, False,
                                "Não encontrado", url)

        except Exception as e:
            logger.warning(f"[olx] Falha: {e}")
            return ScrapeResult(self.store_id, None, False,
                                "Erro", self._build_search_url())
        finally:
            if context:
                await context.close()

    # ------------------------------------------------------------------
    # __NEXT_DATA__ extraction helpers
    # ------------------------------------------------------------------

    def _extract_from_next_data(self, data: dict) -> list[dict]:
        """Walk the __NEXT_DATA__ JSON to find offer entries.
        OLX embeds offers in deeply nested keys that change between builds.
        We walk recursively and extract anything that looks like a listing.
        """
        results = []
        self._walk(data, results)
        return results

    def _walk(self, obj, acc: list):
        if isinstance(obj, dict):
            # OLX listing shapes seen in the wild
            title = obj.get('title') or obj.get('subject') or obj.get('listSubject')
            price = obj.get('price') or obj.get('amount')
            url = obj.get('url') or obj.get('permalink')
            if title is not None:
                p = self._parse_olx_price(price)
                if p is not None and p > 100:
                    acc.append({
                        'title': str(title),
                        'price': p,
                        'url': str(url) if url else None,
                    })
                elif p is None and isinstance(title, str) and len(title) > 5:
                    acc.append({
                        'title': title,
                        'price': p,
                        'url': str(url) if url else None,
                    })
            for v in obj.values():
                self._walk(v, acc)
        elif isinstance(obj, list):
            for item in obj:
                self._walk(item, acc)

    @staticmethod
    def _parse_olx_price(raw) -> float | None:
        if isinstance(raw, (int, float)):
            return float(raw) if raw > 0 else None
        if isinstance(raw, str):
            m = re.search(r'([\d.,]+)', raw)
            if m:
                s = m.group(1)
                # Brazilian: 4.400,00  vs  US/mixed: 4400.00
                if ',' in s:
                    s = s.replace('.', '').replace(',', '.')
                # else: s already uses dot as decimal — keep it
                try:
                    return float(s)
                except ValueError:
                    pass
        return None

    def _pick_best(self, offers: list[dict], fallback_url: str) -> ScrapeResult:
        # Filter meaningful results
        valid = [o for o in offers if o.get('price') and o['price'] > 100]
        if not valid:
            if offers:
                return ScrapeResult(self.store_id, None, False,
                                    "Esgotado / Sem preço", fallback_url)
            return ScrapeResult(self.store_id, None, False,
                                "Não encontrado", fallback_url)
        # Sort cheapest first
        valid.sort(key=lambda x: x['price'])
        best = valid[0]
        return ScrapeResult(
            self.store_id,
            best['price'],
            True,
            "Em estoque",
            best.get('url') or fallback_url,
        )
