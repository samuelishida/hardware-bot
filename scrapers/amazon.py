from __future__ import annotations
import asyncio
import logging
import random
from .base import BaseScraper, ScrapeResult, STEALTH_SCRIPT, USER_AGENTS, VIEWPORTS

logger = logging.getLogger(__name__)

SYSTEM_EXCLUSIONS = [
    'pc gamer', 'pc gaming', 'computador gamer', 'computador completo',
    'desktop gamer', 'workstation', 'pc completo',
    'notebook', 'laptop', 'usado', 'seminovo',
    'extensão', 'extensao', 'cabo', 'adaptador', 'suporte',
    'base', 'cooler', 'pastilha', 'fonte', 'gabinete',
    'riser', 'acessório', 'acessorio',
    'water block', 'waterblock', 'water-block', 'bloco de água', 'bloco de agua',
    'backplate', 'placa traseira', 'ventoinha', 'ventoinhas',
    'dissipador', 'terminal térmico', 'pasta térmica', 'pasta termica',
    'conector', 'bracket', 'protetor', 'capa', 'case para',
    'compatível com', 'compativel com', 'para hdmi', 'módulo de interface',
    'modulo de interface', 'cabo displayport', 'cabo dp', 'cabo hdmi',
    'fibra ótica', 'fibra otica', 'extensor',
]

_EVAL_JS = """(args) => {
    const searchTerm = args.searchTerm;
    const systemExclusions = args.systemExclusions;
    const keywords = searchTerm.replace(/-/g, ' ').toLowerCase().split(' ').filter(Boolean);
    const sigKws = keywords.filter(kw => kw.length >= 2);
    const matchKws = sigKws.length > 0 ? sigKws : keywords;
    const modelKws = keywords.filter(kw => /[0-9]/.test(kw));

    const cards = document.querySelectorAll("div[data-component-type='s-search-result']");
    let results = [];

    for (const card of cards) {
        const nameEl = card.querySelector('h2 span, span.a-size-medium.a-color-base.a-text-normal');
        if (!nameEl) continue;
        const name = nameEl.innerText.trim();
        const nameLower = name.toLowerCase();

        if (systemExclusions.some(p => nameLower.includes(p))) continue;
        if (modelKws.length > 0 && !modelKws.every(kw => nameLower.includes(kw))) continue;
        if (matchKws.length > 0 && !matchKws.every(kw => nameLower.includes(kw))) continue;

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

    // Discard price outliers: keep only results priced >= 30% of the max price.
    // Guards against rogue marketplace listings or accessories matching keywords at 1/5 the real price.
    if (results.length > 1) {
        const maxP = Math.max(...results.filter(r => r.price !== null).map(r => r.price));
        if (maxP > 0) {
            results = results.filter(r => r.price === null || r.price >= maxP * 0.30);
        }
    }

    results.sort((a, b) => b.matchCount - a.matchCount || a.price - b.price);
    return results;
}"""


class AmazonScraper(BaseScraper):
    store_id = "amazon"

    def __init__(self, browser=None, search_term: str = None):
        super().__init__(browser)
        self.search_term = search_term
        self.search_url = f"https://www.amazon.com.br/s?k={self.search_term}"

    async def scrape(self) -> ScrapeResult:
        await asyncio.sleep(random.uniform(2.0, 5.0))
        result = await self._browser_attempt()
        if result is not None:
            return result
        logger.warning("[amazon] Tentativa 1 falhou, tentando novamente...")
        await asyncio.sleep(random.uniform(2.0, 4.0))
        result = await self._browser_attempt()
        if result is not None:
            return result
        return ScrapeResult(self.store_id, None, False, "Erro", self.search_url)

    async def _browser_attempt(self) -> ScrapeResult | None:
        if self.browser is None:
            logger.warning("[amazon] Sem browser compartilhado, pulando.")
            return None

        ua = random.choice(USER_AGENTS)
        vp = random.choice(VIEWPORTS)
        context = None
        try:
            context = await self.browser.new_context(
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
                await page.goto(self.search_url, wait_until="domcontentloaded", timeout=35_000)
            except Exception as e:
                logger.warning(f"[amazon] Timeout de navegação: {e}")
                return None

            title = await page.title()
            if any(kw in title.lower() for kw in ("robot", "captcha", "sorry", "access denied", "digite os caracteres")):
                logger.warning("[amazon] Bloqueado por CAPTCHA.")
                return None

            try:
                await page.wait_for_selector(
                    "div[data-component-type='s-search-result']", timeout=25_000
                )
            except Exception:
                logger.info("[amazon] Nenhum card de produto encontrado.")
                return ScrapeResult(self.store_id, None, False, "Não encontrado", self.search_url)

            products = await page.evaluate(
                _EVAL_JS,
                {"searchTerm": self.search_term, "systemExclusions": SYSTEM_EXCLUSIONS},
            )

            if not products:
                logger.info("[amazon] Produto não encontrado na página.")
                return ScrapeResult(self.store_id, None, False, "Não encontrado", self.search_url)

            logger.info(f"[amazon] {len(products)} produto(s) encontrado(s).")
            for p in products:
                logger.info(f"[amazon] Match: {p['name']!r} | R${p['price']}")

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
            return None
        finally:
            if context:
                await context.close()
