from __future__ import annotations
import asyncio
import logging
import random
from .base import BaseScraper, ScrapeResult, STEALTH_SCRIPT, USER_AGENTS, VIEWPORTS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.amazon.com.br"

SYSTEM_EXCLUSIONS = [
    'pc gamer', 'pc gaming', 'computador gamer', 'computador completo',
    'desktop gamer', 'workstation', 'pc completo',
    'notebook', 'laptop', 'usado', 'seminovo',
    'extensão', 'extensao', 'cabo', 'adaptador', 'suporte',
    'base', 'cooler', 'pastilha', 'fonte', 'gabinete',
    'riser', 'acessório', 'acessorio',
]


class AmazonScraper(BaseScraper):
    store_id = "amazon"

    def __init__(self, browser=None, search_term: str = None):
        super().__init__(browser)
        self.search_term = search_term
        self.search_url = f"https://www.amazon.com.br/s?k={self.search_term}"

    async def scrape(self) -> ScrapeResult:
        await asyncio.sleep(random.uniform(2.0, 5.0))
        return await self._browser_attempt()

    async def _browser_attempt(self) -> ScrapeResult:
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

            try:
                await page.goto(
                    self.search_url, wait_until="domcontentloaded", timeout=35_000
                )
            except Exception as e:
                logger.warning(f"[amazon] Timeout de navegação: {e}")
                return ScrapeResult(self.store_id, None, False, "Timeout", self.search_url)

            title = await page.title()
            if any(kw in title.lower() for kw in ("robot", "captcha", "sorry", "access denied", "digite os caracteres")):
                logger.warning("[amazon] Bloqueado por CAPTCHA.")
                return ScrapeResult(self.store_id, None, False, "Bloqueado", self.search_url)

            # Wait for product cards — Amazon renders them async
            try:
                await page.wait_for_selector(
                    "div[data-component-type='s-search-result']", timeout=25_000
                )
            except Exception:
                logger.info("[amazon] Nenhum card de produto encontrado.")
                return ScrapeResult(self.store_id, None, False, "Não encontrado", self.search_url)

            products = await page.evaluate(
                """(args) => {
                const searchTerm = args.searchTerm;
                const systemExclusions = args.systemExclusions;
                const keywords = searchTerm.replace(/-/g, ' ').toLowerCase().split(' ').filter(Boolean);
                const sigKws = keywords.filter(kw => kw.length >= 2);
                const matchKws = sigKws.length > 0 ? sigKws : keywords;
                const modelKws = keywords.filter(kw => /[0-9]/.test(kw));

                const cards = document.querySelectorAll("div[data-component-type='s-search-result']");
                const results = [];

                for (const card of cards) {
                    const nameEl = card.querySelector('h2 span, span.a-size-medium.a-color-base.a-text-normal');
                    if (!nameEl) continue;
                    const name = nameEl.innerText.trim();
                    const nameLower = name.toLowerCase();

                    // Exclude pre-built systems
                    if (systemExclusions.some(p => nameLower.includes(p))) continue;

                    // All model keywords must match
                    if (modelKws.length > 0 && !modelKws.every(kw => nameLower.includes(kw))) continue;
                    // All significant keywords must match (prevents "4060" alone matching accessories)
                    if (matchKws.length > 0 && !matchKws.every(kw => nameLower.includes(kw))) continue;

                    // Price extraction from structured price elements
                    const priceWhole = card.querySelector('span.a-price-whole');
                    const priceFrac  = card.querySelector('span.a-price-fraction');
                    let price = null;
                    if (priceWhole) {
                        const whole = priceWhole.innerText.trim().replace(/[.,]/g, '').replace(/\\D/g, '');
                        const frac  = priceFrac ? priceFrac.innerText.trim().replace(/\\D/g, '') : '00';
                        const val = parseFloat(whole + '.' + frac.padEnd(2, '0').substring(0, 2));
                        if (!isNaN(val) && val > 10) price = val;
                    }

                    const cardText = card.innerText.toLowerCase();
                    const available = price !== null
                        && !cardText.includes('temporariamente indisponível')
                        && !cardText.includes('sem estoque');

                    const link = card.querySelector('a.a-link-normal[href*="/dp/"], a.a-link-normal.s-no-outline');
                    const href = link ? link.href : null;

                    const matchCount = keywords.filter(kw => nameLower.includes(kw)).length;
                    results.push({ name: name.substring(0, 200), price, available, href, matchCount });
                }

                results.sort((a, b) => b.matchCount - a.matchCount || a.price - b.price);
                return results;
            }""",
                {"searchTerm": self.search_term, "systemExclusions": SYSTEM_EXCLUSIONS},
            )

            if not products:
                logger.info("[amazon] Produto não encontrado na página.")
                return ScrapeResult(self.store_id, None, False, "Não encontrado", self.search_url)

            logger.info(f"[amazon] {len(products)} produto(s) encontrado(s).")

            for p in products:
                if p["available"] and p["price"] is not None:
                    url = p["href"] or self.search_url
                    return ScrapeResult(self.store_id, p["price"], True, "Em estoque", url)

            p = products[0]
            url = p["href"] or self.search_url
            available = p["available"] and p["price"] is not None
            return ScrapeResult(
                self.store_id, p["price"], available,
                "Em estoque" if available else "Indisponível", url,
            )

        except Exception as e:
            logger.error(f"[amazon] Browser attempt falhou: {e}")
            return ScrapeResult(self.store_id, None, False, "Erro", self.search_url)
        finally:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()
