from __future__ import annotations
import logging
import re
import random
from .base import BaseScraper, ScrapeResult

logger = logging.getLogger(__name__)

BASE_URL = "https://www.pichau.com.br"


def _make_slug(name: str) -> str:
    slug = name.lower()
    for ch in ",.()®™":
        slug = slug.replace(ch, "")
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return slug


class PichauScraper(BaseScraper):
    store_id = "pichau"

    def __init__(self, browser=None, search_term: str = None):
        super().__init__(browser)
        self.search_term = search_term
        self.search_url = f"https://www.pichau.com.br/search?q={self.search_term}"

    async def scrape(self) -> ScrapeResult:
        page = await self._new_page()
        try:
            response = await page.goto(
                self.search_url, wait_until="commit", timeout=30_000
            )
            if response is None:
                return ScrapeResult(
                    self.store_id, None, False, "Sem resposta", self.search_url
                )
            html = await response.text()
        except Exception as e:
            logger.warning(f"[pichau] Goto failed: {e}")
            return ScrapeResult(self.store_id, None, False, "Timeout", self.search_url)
        finally:
            await page.context.close()

        if "just a moment" in html[:2000].lower():
            logger.warning("[pichau] Cloudflare challenge detected.")
            return ScrapeResult(self.store_id, None, False, "Cloudflare", self.search_url)

        if len(html) < 5000:
            logger.warning(f"[pichau] Page too small ({len(html)} chars).")
            return ScrapeResult(self.store_id, None, False, "Sem conteúdo", self.search_url)

        products = self._parse_ssr(html)
        if not products:
            logger.info("[pichau] Nenhum produto encontrado no SSR.")
            return ScrapeResult(self.store_id, None, False, "Não encontrado", self.search_url)

        search_keywords = self.search_term.replace("-", " ").split()
        model_keywords = [kw for kw in search_keywords if any(c.isdigit() for c in kw)]

        scored = []
        for name, price, url in products:
            name_lower = name.lower()
            if model_keywords and not all(kw in name_lower for kw in model_keywords):
                continue
            if not any(kw in name_lower for kw in search_keywords):
                continue
            match_count = sum(1 for kw in search_keywords if kw in name_lower)
            scored.append((name, price, url, match_count))

        scored.sort(key=lambda x: (-x[3], x[1] if x[1] is not None else float('inf')))

        for name, price, url, _ in scored:
            available = "esgotado" not in name.lower() and price is not None
            if available:
                return ScrapeResult(self.store_id, price, True, "Em estoque", url)

        if scored:
            name, price, url, _ = scored[0]
            available = "esgotado" not in name.lower() and price is not None
            return ScrapeResult(self.store_id, price, available, "Em estoque" if available else "Esgotado", url)

        logger.info("[pichau] Produto não encontrado após filtro.")
        return ScrapeResult(self.store_id, None, False, "Não encontrado", self.search_url)

    def _parse_ssr(self, html: str) -> list[tuple[str, float | None, str]]:
        products: list[tuple[str, float | None, str]] = []

        script_end = 0
        h2_iter = list(re.finditer(r"<h2[^>]*>([^<]+)</h2>", html))
        for i, m in enumerate(h2_iter):
            name = m.group(1).strip()
            if len(name) < 5:
                continue

            pos = m.end()

            next_h2_start = h2_iter[i + 1].start() if i + 1 < len(h2_iter) else pos + 800
            chunk = html[pos:next_h2_start]

            in_script = False
            for s_match in re.finditer(r"<script[^>]*>.*?</script>", html[:pos], re.DOTALL):
                if pos < s_match.end() and pos > s_match.start():
                    in_script = True
                    break
            if in_script:
                continue

            vista_prices = re.findall(
                r'class="[^"]*price_vista[^"]*"[^>]*>\s*R\$\xa0([\d.,]+)', chunk
            )
            all_prices = re.findall(r"R\$\xa0([\d.,]+)", chunk)
            price = None
            if vista_prices:
                price = self._parse_price(vista_prices[0])
            elif all_prices:
                price = self._parse_price(all_prices[0])

            url = f"{BASE_URL}/produto/{_make_slug(name)}"

            products.append((name, price, url))

        return products