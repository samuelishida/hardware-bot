from __future__ import annotations
import asyncio
import logging
import random
from .base import BaseScraper, ScrapeResult

logger = logging.getLogger(__name__)

BASE_URL = "https://www.amazon.com.br"

SEL_CARD = "div[data-component-type='s-search-result']"
SEL_WHOLE = "span.a-price-whole"
SEL_FRAC = "span.a-price-fraction"
SEL_NAME = "span.a-size-medium.a-color-base.a-text-normal, h2 span"
SEL_LINK = "a.a-link-normal.s-no-outline"


class AmazonScraper(BaseScraper):
    store_id = "amazon"

    def __init__(self, browser=None, search_term: str = None):
        super().__init__(browser)
        self.search_term = search_term
        self.search_url = f"https://www.amazon.com.br/s?k={self.search_term}"

    async def scrape(self) -> ScrapeResult:
        await asyncio.sleep(random.uniform(3.0, 6.0))

        page = await self._new_page()
        try:
            await page.goto(self.search_url, wait_until="domcontentloaded", timeout=35_000)
            await page.wait_for_timeout(random.randint(4000, 8000))
        except Exception as e:
            logger.warning(f"[amazon] Timeout de navegação: {e}")
            return ScrapeResult(self.store_id, None, False, "Timeout", self.search_url)

        title = await page.title()
        if any(kw in title.lower() for kw in ("robot", "captcha", "sorry", "access denied", "digite os caracteres")):
            logger.warning("[amazon] Bloqueado por CAPTCHA — pulando esta varredura.")
            return ScrapeResult(self.store_id, None, False, "Bloqueado", self.search_url)

        try:
            await page.wait_for_selector(SEL_CARD, timeout=15_000)
        except Exception:
            logger.info("[amazon] Nenhum card de produto encontrado (possível bloqueio silencioso).")
            return ScrapeResult(self.store_id, None, False, "Não encontrado", self.search_url)

        cards = await page.query_selector_all(SEL_CARD)
        best: ScrapeResult | None = None

        search_keywords = self.search_term.replace('-', ' ').split()
        model_keywords = [kw for kw in search_keywords if any(c.isdigit() for c in kw)]
        
        accessory_terms = [
            "cooler", "pasta", "thermal", "fan", "kit", "acessório", "water cooler",
            "cabo", "riser", "suporte", "bracket", "adaptador", "case", "gabinete",
            "fonte", "psu", "memória", "ram", "ssd", "hd", "nvme", "m.2",
            "placa mãe", "motherboard", "gabinete"
        ]

        for card in cards:
            name_el = await card.query_selector(SEL_NAME)
            name = (await name_el.inner_text()).lower() if name_el else ""
            
            if any(x in name for x in accessory_terms):
                logger.debug(f"[amazon] Ignorando acessório: {name[:60]}")
                continue
            
            if not any(kw in name for kw in search_keywords):
                continue
            
            # Requer que ao menos uma keyword com dígito (modelo específico) esteja no título
            if model_keywords and not any(kw in name for kw in model_keywords):
                logger.debug(f"[amazon] Modelo não corresponde: {name[:60]}")
                continue

            whole_el = await card.query_selector(SEL_WHOLE)
            frac_el = await card.query_selector(SEL_FRAC)
            if whole_el:
                whole = (await whole_el.inner_text()).strip().replace(".", "").replace(",", "")
                frac = (await frac_el.inner_text()).strip() if frac_el else "00"
                try:
                    price: float | None = float(f"{whole}.{frac}")
                except ValueError:
                    price = None
            else:
                price = None

            link_el = await card.query_selector(SEL_LINK)
            href = await link_el.get_attribute("href") if link_el else None
            url = f"{BASE_URL}{href}" if href and not href.startswith("http") else href or self.search_url

            card_text = (await card.inner_text()).lower()
            available = (
                "temporariamente indisponível" not in card_text
                and ("adicionar ao carrinho" in card_text or "comprar agora" in card_text)
                or (price is not None and "indisponível" not in card_text)
            )
            stock_label = "Em estoque" if available else "Indisponível"

            candidate = ScrapeResult(self.store_id, price, available, stock_label, url)
            if best is None:
                best = candidate
            elif available and not best.available:
                best = candidate
            elif available and best.available and price and best.price and price < best.price:
                best = candidate

        if best is None:
            logger.info("[amazon] Produto não encontrado na página.")
            return ScrapeResult(self.store_id, None, False, "Não encontrado", self.search_url)

        return best
