"""
tests/test_scrapers.py — Unit tests for scrapers.

Tests scraper logic without real HTTP requests or browser launches.
"""

import pytest
from unittest.mock import MagicMock

from scrapers.base import BaseScraper, ScrapeResult
from scrapers.kabum import KabumScraper
from scrapers.pichau import PichauScraper
from scrapers.amazon import AmazonScraper
from scrapers.mercadolivre import MercadoLivreScraper


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


class TestMercadoLivreScraper:
    """Tests for MercadoLivreScraper."""

    def test_init_with_search_term(self):
        scraper = MercadoLivreScraper(search_term="rx-7900-xtx")
        assert scraper.store_id == "mercadolivre"
        assert scraper.search_term == "rx-7900-xtx"

    def test_init_no_search_term(self):
        scraper = MercadoLivreScraper()
        assert scraper.store_id == "mercadolivre"
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
        assert result.available is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
