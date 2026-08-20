"""
tests/test_scrapers.py — Unit tests for scrapers.

Tests scraper logic without real HTTP requests or browser launches.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from scrapers.base import BaseScraper, ScrapeResult
from scrapers.kabum import KabumScraper
from scrapers.pichau import PichauScraper
from scrapers.amazon import AmazonScraper
from scrapers.terabyte import TeraScraper


def _fake_browser(products: list[dict]):
    """Fake Lightpanda browser facade que devolve ``products`` no evaluate."""
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=products)
    page.content = AsyncMock(return_value="<html>normal</html>")
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.title = AsyncMock(return_value="Loja")
    page.set_extra_http_headers = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.add_init_script = AsyncMock()
    context.close = AsyncMock()
    page.context = context
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    return browser


def _fake_pichau_browser(html: str):
    """Fake browser para Pichau: ``page.goto`` devolve response com ``.text()``."""
    page = MagicMock()
    response = MagicMock()
    response.text = AsyncMock(return_value=html)
    page.goto = AsyncMock(return_value=response)
    page.set_extra_http_headers = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.add_init_script = AsyncMock()
    context.close = AsyncMock()
    page.context = context
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    return browser


class TestBaseScraper:
    """Tests for BaseScraper utility methods."""
    
    def test_parse_price_brl_standard(self):
        """Test parsing standard BRL price."""
        scraper = BaseScraper()
        assert scraper._parse_price("R$ 1.234,56") == 1234.56
        assert scraper._parse_price("R$ 100,00") == 100.0
        assert scraper._parse_price("R$ 1.000,99") == 1000.99
    
    def test_parse_price_pix(self):
        """Test parsing PIX price."""
        scraper = BaseScraper()
        assert scraper._parse_price("R$ 999,99 à vista no PIX") == 999.99
        assert scraper._parse_price("999,99 no pix") == 999.99
    
    def test_parse_price_none(self):
        """Test parsing invalid prices."""
        scraper = BaseScraper()
        assert scraper._parse_price(None) is None
        assert scraper._parse_price("") is None
        assert scraper._parse_price("Indisponível") is None
    
    def test_parse_price_decimal_comma(self):
        """Test parsing price with comma as decimal separator."""
        scraper = BaseScraper()
        assert scraper._parse_price("1.234,56") == 1234.56
        assert scraper._parse_price("100,00") == 100.0
    
    def test_parse_price_decimal_point(self):
        """Test parsing price with point as decimal separator."""
        scraper = BaseScraper()
        assert scraper._parse_price("1234.56") == 1234.56


class TestKabumScraper:
    """Tests for KabumScraper."""

    def test_init_with_search_term(self):
        scraper = KabumScraper(search_term="rtx-4060-ti")
        assert scraper.store_id == "kabum"
        assert scraper.search_term == "rtx-4060-ti"
        assert "rtx-4060-ti" in scraper.search_url

    def test_init_no_search_term(self):
        scraper = KabumScraper()
        assert scraper.store_id == "kabum"
        assert scraper.search_term is None


class TestPichauScraper:
    """Tests for PichauScraper."""

    def test_init_with_search_term(self):
        scraper = PichauScraper(search_term="rx-7900-xtx")
        assert scraper.store_id == "pichau"
        assert scraper.search_term == "rx-7900-xtx"

    def test_init_no_search_term(self):
        scraper = PichauScraper()
        assert scraper.store_id == "pichau"
        assert scraper.search_term is None


class TestAmazonScraper:
    """Tests for AmazonScraper."""

    def test_init_with_search_term(self):
        scraper = AmazonScraper(search_term="rtx-4060")
        assert scraper.store_id == "amazon"
        assert scraper.search_term == "rtx-4060"
        assert "rtx-4060" in scraper.search_url

    def test_init_no_search_term(self):
        scraper = AmazonScraper()
        assert scraper.store_id == "amazon"
        assert scraper.search_term is None


class TestScrapeResult:
    """Tests for ScrapeResult dataclass."""
    
    def test_create_result(self):
        """Test creating a ScrapeResult."""
        result = ScrapeResult(
            store_id="kabum",
            price=1500.0,
            available=True,
            stock_label="Em estoque",
            url="https://kabum.com/product",
        )
        assert result.store_id == "kabum"
        assert result.price == 1500.0
        assert result.available is True
        assert result.title is None

    def test_create_result_none_price(self):
        """Test creating result with None price."""
        result = ScrapeResult(
            store_id="kabum",
            price=None,
            available=False,
            stock_label="Não encontrado",
            url=None,
        )
        assert result.price is None


class TestRelevanceFiltering:
    """Inc 2: scrapers rejeitam acessório e setam title via is_relevant."""

    @pytest.mark.asyncio
    async def test_kabum_rejects_accessory_and_sets_title(self):
        products = [
            {"name": "Adaptador USB PS5 PS Link", "price": 119.0, "available": True,
             "href": "https://kabum.com.br/produto/1/adaptador", "matchCount": 1},
            {"name": "Console PS5 Slim", "price": 4799.90, "available": True,
             "href": "https://kabum.com.br/produto/2/console", "matchCount": 2},
        ]
        scraper = KabumScraper(browser=_fake_browser(products), search_term="ps5")
        with patch("scrapers.kabum.get_terms", new=AsyncMock(return_value=[])):
            result = await scraper.scrape()
        assert result.title == "Console PS5 Slim"
        assert result.price == 4799.90
        assert result.available is True

    @pytest.mark.asyncio
    async def test_kabum_all_accessories_returns_not_found(self):
        products = [
            {"name": "Adaptador USB PS5 PS Link", "price": 119.0, "available": True,
             "href": "https://kabum.com.br/produto/1/adaptador", "matchCount": 1},
        ]
        scraper = KabumScraper(browser=_fake_browser(products), search_term="ps5")
        with patch("scrapers.kabum.get_terms", new=AsyncMock(return_value=[])):
            result = await scraper.scrape()
        assert result.available is False
        assert result.price is None

    @pytest.mark.asyncio
    async def test_amazon_rejects_accessory_and_sets_title(self):
        products = [
            {"name": "Cabo HDMI PS5 2m", "price": 49.0, "available": True,
             "href": "https://amazon.com.br/dp/1", "matchCount": 1},
            {"name": "Console PS5 Slim", "price": 4799.90, "available": True,
             "href": "https://amazon.com.br/dp/2", "matchCount": 2},
        ]
        scraper = AmazonScraper(browser=_fake_browser(products), search_term="ps5")
        with patch("scrapers.amazon.get_terms", new=AsyncMock(return_value=[])):
            result = await scraper.scrape()
        assert result.title == "Console PS5 Slim"
        assert result.price == 4799.90
        assert result.available is True

    @pytest.mark.asyncio
    async def test_pichau_rejects_accessory_and_sets_title(self):
        base = (
            '<h2>Adaptador USB PS5 PS Link</h2><div class="price_vista">R$\xa0119,00</div>'
            '<h2>Console PS5 Slim</h2><div class="price_vista">R$\xa04799,90</div>'
        )
        html = base + "<!-- padding -->" * 600  # > 5000 chars (pichau exige)
        scraper = PichauScraper(browser=_fake_pichau_browser(html), search_term="ps5")
        with patch("scrapers.pichau.get_terms", new=AsyncMock(return_value=[])):
            result = await scraper.scrape()
        assert result.title == "Console PS5 Slim"
        assert result.price == 4799.90

    @pytest.mark.asyncio
    async def test_terabyte_rejects_accessory_and_sets_title(self):
        products = [
            {"name": "Cabo HDMI PS5 2m", "price": 49.0, "available": True,
             "url": "https://terabyte.com.br/1", "matchCount": 1},
            {"name": "Console PS5 Slim", "price": 4799.90, "available": True,
             "url": "https://terabyte.com.br/2", "matchCount": 2},
        ]
        scraper = TeraScraper(browser=_fake_browser(products), search_term="ps5")
        with patch("scrapers.terabyte.get_terms", new=AsyncMock(return_value=[])):
            result = await scraper.scrape()
        assert result.title == "Console PS5 Slim"
        assert result.price == 4799.90


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
