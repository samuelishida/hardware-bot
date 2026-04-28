#!/usr/bin/env python3
"""Teste local dos scrapers para validar bypass de anti-bot."""

import asyncio
import logging
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def test_scraper(scraper_cls, search_term: str = "rx 7900 xtx"):
    """Testa um scraper individual."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testando {scraper_cls.store_id.upper()} com '{search_term}'")
    print(f"{'='*60}")
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ]
        )
        
        try:
            async with scraper_cls(browser=browser, search_term=search_term) as scraper:
                result = await scraper.scrape()
                
            logger.info(f"Resultado: {result}")
            print(f"\n  Store: {result.store_id}")
            print(f"  Preço: R$ {result.price:.2f}" if result.price else "  Preço: Não encontrado")
            print(f"  Disponível: {'Sim' if result.available else 'Não'}")
            print(f"  Estoque: {result.stock_label}")
            print(f"  URL: {result.url}")
            
            return result
        except Exception as e:
            logger.error(f"Erro ao testar {scraper_cls.store_id}: {e}")
            print(f"\n  ERRO: {e}")
            return None
        finally:
            await browser.close()


async def main():
    from scrapers.kabum import KabumScraper
    from scrapers.pichau import PichauScraper
    from scrapers.terabyte import TeraScraper
    from scrapers.amazon import AmazonScraper
    from scrapers.mercadolivre import MercadoLivreScraper
    
    scrapers = [
        KabumScraper,
        PichauScraper,
        TeraScraper,
        AmazonScraper,
        MercadoLivreScraper,
    ]
    
    results = {}
    for scraper_cls in scrapers:
        result = await test_scraper(scraper_cls)
        results[scraper_cls.store_id] = result
        await asyncio.sleep(3)  # Delay entre testes
    
    print(f"\n{'='*60}")
    print("RESUMO:")
    print(f"{'='*60}")
    for store_id, result in results.items():
        status = "✓" if result and result.price else "✗"
        price_str = f"R$ {result.price:.2f}" if result and result.price else "Não encontrado"
        print(f"  {status} {store_id}: {price_str}")


if __name__ == "__main__":
    asyncio.run(main())
