"""
scrapers/__init__.py — Scraper registry.

Single source of truth for all scraper classes. Import from here
instead of referencing individual scraper modules directly.
"""

from scrapers.kabum import KabumScraper
from scrapers.pichau import PichauScraper
from scrapers.terabyte import TeraScraper
from scrapers.amazon import AmazonScraper
from scrapers.mercadolivre import MercadoLivreScraper, MercadoLivreUsadoScraper

# All scrapers that need a shared Playwright browser instance
BROWSER_SCRAPERS = [
    KabumScraper,
    PichauScraper,
    TeraScraper,
    AmazonScraper,
    MercadoLivreScraper,
    MercadoLivreUsadoScraper,
]

# Scrapers that use HTTP directly (none currently)
HTTP_SCRAPERS = []
