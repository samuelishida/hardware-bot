"""
tests/test_product_manager.py — Unit tests for core/product_manager.py.
"""

import pytest
from core.product_manager import ProductManager, Product


class TestProductManager:
    """Tests for ProductManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.pm = ProductManager()
    
    def test_parse_product_name_simple(self):
        """Test parsing a simple product name."""
        product = self.pm.parse_product_name("RTX 4060")
        assert product.name == "RTX 4060"
        assert product.search_term == "rtx-4060"
    
    def test_parse_product_name_complex(self):
        """Test parsing a complex product name."""
        product = self.pm.parse_product_name("AMD Ryzen 5 5700X3D")
        assert product.name == "AMD Ryzen 5 5700X3D"
        assert product.search_term == "ryzen-5-5700x3d"
    
    def test_parse_product_name_with_special_chars(self):
        """Test parsing product name with special characters."""
        product = self.pm.parse_product_name("iPhone 15 Pro Max 256GB")
        assert product.name == "iPhone 15 Pro Max 256GB"
        assert product.search_term == "iphone-15-pro-max-256gb"
    
    def test_normalize_search_term(self):
        """Test search term normalization."""
        assert self.pm.normalize_search_term("RTX 4060 Ti") == "rtx-4060-ti"
        assert self.pm.normalize_search_term("  iPhone 15  ") == "iphone-15"
    
    def test_format_price_brl(self):
        """Test BRL price formatting."""
        assert self.pm.format_price_brl(1234.56) == "R$ 1.234,56"
        assert self.pm.format_price_brl(None) == "Indisponível"
    
    def test_get_search_url(self):
        """Test search URL generation for all stores."""
        search_term = "rtx-4060"
        
        kabum_url = self.pm.get_search_url("kabum", search_term)
        assert "rtx-4060" in kabum_url
        assert "kabum.com.br" in kabum_url
        
        pichau_url = self.pm.get_search_url("pichau", search_term)
        assert "rtx-4060" in pichau_url
        assert "pichau.com.br" in pichau_url
        
        terabyte_url = self.pm.get_search_url("terabyte", search_term)
        assert "rtx-4060" in terabyte_url
        assert "terabyteshop.com.br" in terabyte_url
        
        amazon_url = self.pm.get_search_url("amazon", search_term)
        assert "rtx-4060" in amazon_url
        assert "amazon.com.br" in amazon_url
        
        ml_url = self.pm.get_search_url("mercadolivre", search_term)
        assert "rtx-4060" in ml_url
        assert "mercadolivre.com.br" in ml_url
    
    def test_get_store_display_names(self):
        """Test store display names."""
        names = self.pm.get_store_display_names()
        assert names["kabum"] == "KaBuM!"
        assert names["pichau"] == "Pichau"
        assert names["terabyte"] == "Terabyte Shop"
        assert names["mercadolivre"] == "Mercado Livre"
        assert names["amazon"] == "Amazon BR"
    
    def test_get_store_colors(self):
        """Test store colors are valid hex values."""
        colors = self.pm.get_store_colors()
        for store_id, color in colors.items():
            assert isinstance(color, int)
            assert 0 <= color <= 0xFFFFFF


class TestProduct:
    """Tests for Product dataclass."""
    
    def test_product_creation(self):
        """Test creating a Product instance."""
        product = Product(name="RTX 4060 Ti", search_term="rtx-4060-ti")
        assert product.name == "RTX 4060 Ti"
        assert product.search_term == "rtx-4060-ti"
    
    def test_product_equality(self):
        """Test Product equality comparison."""
        p1 = Product(name="RTX 4060", search_term="rtx-4060")
        p2 = Product(name="RTX 4060", search_term="rtx-4060")
        p3 = Product(name="RTX 4060 Ti", search_term="rtx-4060-ti")
        
        assert p1 == p2
        assert p1 != p3
