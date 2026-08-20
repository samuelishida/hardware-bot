"""core/executor.py — Scraper execution engine.

Runs all scrapers sequentially sharing one browser instance (1 GB RAM constraint).
Inc 2: refatorado para ``scrape_product_detailed`` que retorna :class:`StoreOutcome`
(classificados) e um wrapper ``scrape_product`` de compatibilidade com o legado.
Inc 4 (Lightpanda): troca o Playwright/Chromium pelo ``LightpandaBrowser`` (facade
CDP em ``core/browser.py``). Mesma assinatura, mesmo loop sequencial + timeout.
"""

from __future__ import annotations
import asyncio
import logging

from core.browser import LightpandaBrowser
from scrapers.base import ScrapeResult
from scrapers.errors import ScrapeErrorKind, StoreOutcome, looks_anti_bot


logger = logging.getLogger(__name__)

SCRAPER_TIMEOUT = 90


def _classify(store_id: str, result) -> StoreOutcome:
    """Classifica o resultado de um scraper individual em um ``StoreOutcome``."""
    if result is None:
        return StoreOutcome(store_id=store_id, result=None, kind=ScrapeErrorKind.PARSE_ERROR,
                            detail="preço ilegível")
    if result.price is not None and result.price > 0:
        return StoreOutcome(store_id=store_id, result=result, kind=ScrapeErrorKind.OK)
    if looks_anti_bot(result.stock_label or ""):
        # Precedência documentada em scrapers/errors.py: antibot > not_found.
        # Um item indisponível com stock_label de captcha/Cloudflare é antibot,
        # não not_found (antibot é terminal → não re-scrapeia).
        return StoreOutcome(store_id=store_id, result=result, kind=ScrapeErrorKind.ANTI_BOT,
                            detail="detecção antibot")
    if result.available is False:
        return StoreOutcome(store_id=store_id, result=None, kind=ScrapeErrorKind.NOT_FOUND,
                            detail="item não listado")
    return StoreOutcome(store_id=store_id, result=None, kind=ScrapeErrorKind.PARSE_ERROR,
                        detail=str(result.stock_label or "preço ilegível"))


async def scrape_product_detailed(  # noqa: D417 -- Inc 2; returns classified outcomes
    browser_scraper_classes: list,
    http_scraper_classes: list,
    search_term: str,
) -> list["StoreOutcome"]:
    """Execute all scrapers sequentially sharing one browser.

    Returns a :class:`StoreOutcome` per store com ``kind`` classificado (ok/timeout/antibot/
    not_found/parse_error/unknown), para que o orquestrador MAS decida se re-scrapeia ou não.
    O wrapper legado :func:`scrape_product` filtra apenas os OKs e retorna ``ScrapeResult``s,
    mantendo compatibilidade com quem chama ``core.executor.scrape_product``.

    Critical path: Inc 2 → `agents.nodes.scraper_node`. DAG dependência: antes do Inc 5.
    """
    all_classes = list(browser_scraper_classes) + list(http_scraper_classes)
    outcomes: list["StoreOutcome"] = []

    browser = LightpandaBrowser()
    try:
        await browser.start()
        for cls in all_classes:
            store_id = getattr(cls, 'store_id', cls.__name__)
            try:
                scraper = cls(browser=browser, search_term=search_term)
                async with scraper:
                    result = await asyncio.wait_for(
                        scraper.scrape(), timeout=SCRAPER_TIMEOUT
                    )
                outcomes.append(_classify(store_id, result))

            except asyncio.TimeoutError:
                logger.warning(f"[{store_id}] Timeout após {SCRAPER_TIMEOUT}s — re-scrapeável.")
                outcomes.append(StoreOutcome(store_id=store_id, result=None, kind=ScrapeErrorKind.TIMEOUT, detail=f"timeout em {SCRAPER_TIMEOUT}s"))
            except Exception as e:  # pragma: no cover - path de erro genérico; logado pelo caller MAS
                logger.error(f"[{store_id}] Falha inesperada: {e}", exc_info=True)
                outcomes.append(StoreOutcome(store_id=store_id, result=None, kind=ScrapeErrorKind.UNKNOWN, detail=str(e)))
    finally:
        await browser.stop()

    return outcomes


async def scrape_product(  # type: ignore[no-redef] -- legacy wrapper (compat)
    browser_scraper_classes: list,
    http_scraper_classes: list,
    search_term: str,
) -> list["ScrapeResult"]:
    """Wrapper legado: chama ``scrape_product_detailed`` e filtra apenas outcomes OK.

    Mantém compatibilidade com todo código que espera ``core.executor.scrape_product()``
    retornando ``list[ScrapeResult]``, inclusive tests existentes do executor/test_scrapers.
    """
    return [o.result for o in await scrape_product_detailed(
        browser_scraper_classes, http_scraper_classes, search_term) if o.kind == ScrapeErrorKind.OK and o.result]


__all__ = ["scrape_product", "scrape_product_detailed"]
