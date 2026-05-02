from __future__ import annotations
import logging
import asyncio
import random
from .base import BaseScraper, ScrapeResult

logger = logging.getLogger(__name__)

# PC / pre-built system exclusion (prevents matching "PC Gamer com Ryzen 5" instead of the CPU)
SYSTEM_EXCLUSIONS = [
    'pc gamer', 'pc gaming', 'computador gamer', 'computador completo',
    'desktop gamer', 'workstation', 'pc completo',
    'notebook', 'laptop', 'usado', 'seminovo', 'cpu branco',
]


class KabumScraper(BaseScraper):
    store_id = "kabum"

    def __init__(self, browser=None, search_term: str = None):
        super().__init__(browser)
        self.search_term = search_term
        self.search_url = f"https://www.kabum.com.br/busca/{self.search_term}"

    async def scrape(self) -> ScrapeResult:
        await asyncio.sleep(random.uniform(1.0, 3.0))

        page = await self._new_page()
        try:
            try:
                await page.goto(
                    self.search_url, wait_until="domcontentloaded", timeout=30_000
                )
            except Exception as e:
                logger.warning(f"[kabum] Goto failed: {e}")
                return ScrapeResult(self.store_id, None, False, "Timeout", self.search_url)

            # Wait for product cards to render (KaBuM hydrates React async)
            try:
                await page.wait_for_selector(
                    'a[href*="/produto/"]', timeout=30_000
                )
                # Extra wait for card text/prices to populate after hydration
                await page.wait_for_timeout(8000)
            except Exception:
                # Fallback: try waiting longer under memory pressure
                logger.info("[kabum] Product cards slow to render, waiting longer...")
                try:
                    await page.wait_for_selector(
                        'a[href*="/produto/"]', timeout=60_000
                    )
                    await page.wait_for_timeout(8000)
                except Exception:
                    logger.info("[kabum] Product cards did not render.")
                    return ScrapeResult(self.store_id, None, False, "Não encontrado", self.search_url)

            html = await page.content()
            if "just a moment" in html[:2000].lower():
                logger.warning("[kabum] Cloudflare challenge detected.")
                return ScrapeResult(self.store_id, None, False, "Cloudflare", self.search_url)

            products = await page.evaluate(
                """(args) => {
                const searchTerm = args.searchTerm;
                const systemExclusions = args.systemExclusions;
                const keywords = searchTerm.replace(/-/g, ' ').toLowerCase().split(' ').filter(Boolean);
                const sigKws = keywords.filter(kw => kw.length >= 2);
                const matchKws = sigKws.length > 0 ? sigKws : keywords;
                const modelKws = keywords.filter(kw => /[0-9]/.test(kw));

                // KaBuM product cards are <a href="/produto/{id}/name"> elements
                const cards = Array.from(document.querySelectorAll('a[href*="/produto/"]'))
                    .filter(a => /\\/produto\\/\\d+\\//.test(a.href));

                const results = [];
                for (const card of cards) {
                    const cardText = (card.innerText || '').trim();
                    if (!cardText || cardText.length < 10) continue;
                    const textLower = cardText.toLowerCase();

                    // Extract product name first (first meaningful line containing a keyword,
                    // or first long line as fallback) — filter keywords against name only,
                    // not full card text (avoids accessories matching via description)
                    const lines = cardText.split('\\n').map(l => l.trim()).filter(l => l.length > 10);
                    const name = lines.find(l => keywords.some(kw => l.toLowerCase().includes(kw)))
                        || lines.find(l => l.length > 20)
                        || lines[0] || '';
                    const nameLower = name.toLowerCase();

                    // System exclusions use full card text (broader safety net)
                    if (systemExclusions.some(p => textLower.includes(p))) continue;

                    // Keyword matching on product name only — prevents accessories matching
                    // via compatibility notes in the card description
                    if (modelKws.length > 0 && !modelKws.every(kw => nameLower.includes(kw))) continue;
                    if (matchKws.length > 0 && !matchKws.every(kw => nameLower.includes(kw))) continue;

                    // Price extraction: find all R$ amounts, filter out installment fragments
                    const allPrices = Array.from(
                        textLower.matchAll(/r\\$[\\s\\u00a0\\n]*(\\d[\\d.]*,\\d{2})/g)
                    ).map(m => parseFloat(m[1].replace(/\\./g, '').replace(',', '.')))
                     .filter(v => !isNaN(v) && v > 10);

                    let price = null;
                    if (allPrices.length > 0) {
                        const maxP = Math.max(...allPrices);
                        // Keep prices >= 60% of max to exclude installment/cashback/discount fragments
                        const validPrices = allPrices.filter(p => p >= Math.max(30, maxP * 0.60));
                        if (validPrices.length > 0) price = Math.min(...validPrices);
                    }

                    const available = price !== null
                        && !textLower.includes('indisponível')
                        && !textLower.includes('esgotado');

                    const matchCount = keywords.filter(kw => nameLower.includes(kw)).length;
                    results.push({
                        href: card.href || '',
                        price, available,
                        name: name.substring(0, 200),
                        matchCount,
                    });
                }

                results.sort((a, b) => b.matchCount - a.matchCount || a.price - b.price);
                return results;
            }""",
                {"searchTerm": self.search_term, "systemExclusions": SYSTEM_EXCLUSIONS},
            )

            if not products:
                logger.info("[kabum] Nenhum produto encontrado na página de resultados.")
                return ScrapeResult(self.store_id, None, False, "Não encontrado", self.search_url)

            logger.info(f"[kabum] {len(products)} produto(s) encontrado(s).")

            for p in products:
                if p["available"] and p["price"] is not None:
                    url = p["href"] if p["href"].startswith("http") else f"https://www.kabum.com.br{p['href']}"
                    return ScrapeResult(self.store_id, p["price"], True, "Em estoque", url)

            p = products[0]
            url = p["href"] if p["href"].startswith("http") else f"https://www.kabum.com.br{p['href']}"
            available = "esgotado" not in (p.get("name", "") or "").lower() and p["price"] is not None
            return ScrapeResult(
                self.store_id, p["price"], available,
                "Em estoque" if available else "Esgotado", url,
            )
        finally:
            await page.context.close()
