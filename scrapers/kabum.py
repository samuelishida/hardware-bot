from __future__ import annotations
import logging
import asyncio
import random
from .base import BaseScraper, ScrapeResult

logger = logging.getLogger(__name__)


class KabumScraper(BaseScraper):
    store_id = "kabum"

    def __init__(self, browser=None, search_term: str = None):
        super().__init__(browser)
        self.search_term = search_term
        self.search_url = f"https://www.kabum.com.br/busca/{self.search_term}"

    async def scrape(self) -> ScrapeResult:
        await asyncio.sleep(random.uniform(2.0, 5.0))

        page = await self._new_page()
        try:
            await page.goto(self.search_url, wait_until="commit", timeout=30_000)
            await page.wait_for_timeout(random.randint(10000, 14000))
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(random.randint(3000, 5000))
        except Exception as e:
            logger.warning(f"[kabum] Timeout ao carregar página: {e}")
            return ScrapeResult(self.store_id, None, False, "Timeout", self.search_url)

        products = await page.evaluate("""(searchTerm) => {
            const keywords = searchTerm.replace(/-/g, ' ').split(' ');
            const modelKeywords = keywords.filter(kw => /[0-9]/.test(kw));

            // Each product card is a <main> element containing one product link
            const cards = document.querySelectorAll("main");
            const results = [];

            for (const card of cards) {
                const cardText = (card.innerText || '').toLowerCase();
                const link = card.querySelector("a[href*='/produto/']");
                if (!link) continue;

                const href = link.getAttribute('href') || '';

                // ALL model keywords must match — prevents wrong product category matches
                if (modelKeywords.length > 0 && !modelKeywords.every(kw => cardText.includes(kw))) continue;
                if (!keywords.some(kw => cardText.includes(kw))) continue;

                // Extract price from card's innerText
                // KaBuM prices: R$ 1.699,99 or R$4.499,00
                const priceMatch = cardText.match(/r\\$\\s*([\\d.,]+)/);
                let price = null;
                if (priceMatch) {
                    const raw = priceMatch[1].replace(/\\./g, '').replace(',', '.');
                    price = parseFloat(raw);
                    if (isNaN(price) || price < 10) price = null;
                }

                const available = price !== null && !cardText.includes('indisponível');

                // Get product name from card text (first meaningful line)
                const nameMatch = card.innerText.match(/^(.{10,80})$/m);
                const name = nameMatch ? nameMatch[1].trim() : href.replace('/produto/', '').replace(/\\d+\\//, '').replace(/-/g, ' ');

                // Relevance: more keywords in name = better match
                const nameLower = name.toLowerCase();
                const matchCount = keywords.filter(kw => nameLower.includes(kw)).length;

                results.push({ href, price, available, name: name.substring(0, 200), matchCount });
            }
            // Sort by relevance then price
            results.sort((a, b) => b.matchCount - a.matchCount || a.price - b.price);
            return results;
        }""", self.search_term)

        if not products:
            logger.info("[kabum] Produto não encontrado na página de resultados.")
            return ScrapeResult(self.store_id, None, False, "Não encontrado", self.search_url)

        logger.info(f"[kabum] {len(products)} produto(s) encontrado(s).")
        # Results already sorted by relevance (most keyword matches in name), then price
        for p in products:
            if not p['available'] or p['price'] is None:
                continue
            url = f"https://www.kabum.com.br{p['href']}" if p['href'] else self.search_url
            return ScrapeResult(self.store_id, p['price'], True, "Em estoque", url)

        # No in-stock result — return first product anyway
        p = products[0]
        url = f"https://www.kabum.com.br{p['href']}" if p['href'] else self.search_url
        stock_label = "Em estoque" if p['available'] else "Indisponível"
        return ScrapeResult(self.store_id, p['price'], p['available'], stock_label, url)