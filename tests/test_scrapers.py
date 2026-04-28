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
    
    def test_init_default(self):
        """Test default initialization."""
        scraper = KabumScraper()
        assert scraper.store_id == "kabum"
        assert scraper.search_term == "ryzen-5-5700x3d"
        assert "ryzen-5-5700x3d" in scraper.search_url
    
    def test_init_custom_search_term(self):
        """Test initialization with custom search term."""
        scraper = KabumScraper(search_term="rtx-4060-ti")
        assert scraper.search_term == "rtx-4060-ti"
        assert "rtx-4060-ti" in scraper.search_url


class TestPichauScraper:
    """Tests for PichauScraper."""
    
    def test_init_default(self):
        """Test default initialization."""
        scraper = PichauScraper()
        assert scraper.store_id == "pichau"
        assert scraper.search_term == "ryzen-5-5700x3d"
    
    def test_init_custom_search_term(self):
        """Test initialization with custom search term."""
        scraper = PichauScraper(search_term="rx-7900-xtx")
        assert scraper.search_term == "rx-7900-xtx"


class TestAmazonScraper:
    """Tests for AmazonScraper."""
    
    def test_init_default(self):
        """Test default initialization."""
        scraper = AmazonScraper()
        assert scraper.store_id == "amazon"
        assert "ryzen-5700x3d" in scraper.search_url
    
    def test_init_custom_search_term(self):
        """Test initialization with custom search term."""
        scraper = AmazonScraper(search_term="rtx-4060")
        assert scraper.search_term == "rtx-4060"
        assert "rtx-4060" in scraper.search_url


class TestMercadoLivreScraper:
    """Tests for MercadoLivreScraper."""
    
    def test_init_default(self):
        """Test default initialization."""
        scraper = MercadoLivreScraper()
        assert scraper.store_id == "mercadolivre"
        assert scraper.search_term == "ryzen-5-5700x3d"
        assert "ryzen+5+5700x3d" in scraper.api_url
    
    def test_init_custom_search_term(self):
        """Test initialization with custom search term."""
        scraper = MercadoLivreScraper(search_term="rx-7900-xtx")
        assert scraper.search_term == "rx-7900-xtx"
        assert "rx+7900+xtx" in scraper.api_url
    
    @pytest.mark.asyncio
    async def test_scrape_api_success(self):
        """Test successful API scrape."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "AMD Ryzen 5 5700X3D",
                    "price": 1500.0,
                    "condition": "new",
                    "available_quantity": 10,
                    "permalink": "https://ml.com/product",
                }
            ]
        }
        
        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            
            scraper = MercadoLivreScraper(search_term="ryzen-5-5700x3d")
            result = await scraper.scrape()
            
            assert result.store_id == "mercadolivre"
            assert result.price == 1500.0
            assert result.available is True
    
    @pytest.mark.asyncio
    async def test_scrape_api_403_no_fallback(self):
        """Test API returns 403 - no fallback, just error."""
        from httpx import HTTPStatusError
        
        mock_response = MagicMock()
        mock_response.status_code = 403
        
        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            mock_client.get.side_effect = HTTPStatusError(
                "403 Forbidden",
                request=MagicMock(),
                response=mock_response
            )
            
            scraper = MercadoLivreScraper(search_term="ryzen-5-5700x3d")
            result = await scraper.scrape()
            
            assert result.price is None
            assert result.available is False
            assert result.stock_label == "Erro de rede"


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
