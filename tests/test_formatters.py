"""
tests/test_formatters.py — Unit tests for utils/formatters.py.
"""

import pytest
from utils.formatters import format_price_brl, format_store_name, normalize_search_term


class TestFormatPriceBrl:
    """Tests for format_price_brl function."""
    
    def test_format_valid_price(self):
        assert format_price_brl(1234.56) == "R$ 1.234,56"
    
    def test_format_zero_price(self):
        assert format_price_brl(0) == "R$ 0,00"
    
    def test_format_none_price(self):
        assert format_price_brl(None) == "Indisponível"
    
    def test_format_large_price(self):
        assert format_price_brl(1234567.89) == "R$ 1.234.567,89"
    
    def test_format_small_price(self):
        assert format_price_brl(0.99) == "R$ 0,99"


class TestNormalizeSearchTerm:
    """Tests for normalize_search_term function."""
    
    def test_normalize_simple(self):
        assert normalize_search_term("RTX 4060") == "rtx-4060"
    
    def test_normalize_with_spaces(self):
        assert normalize_search_term("iPhone 15 Pro") == "iphone-15-pro"
    
    def test_normalize_mixed_case(self):
        assert normalize_search_term("Ryzen 5 5700X3D") == "ryzen-5-5700x3d"
    
    def test_normalize_extra_spaces(self):
        assert normalize_search_term("  RTX  4060  ") == "rtx-4060"
    
    def test_normalize_already_lowercase(self):
        assert normalize_search_term("rtx-4060") == "rtx-4060"


class TestFormatStoreName:
    """Tests for format_store_name function."""
    
    def test_format_kabum(self):
        assert format_store_name("kabum") == "KaBuM!"
    
    def test_format_pichau(self):
        assert format_store_name("pichau") == "Pichau"
    
    def test_format_terabyte(self):
        assert format_store_name("terabyte") == "Terabyte Shop"
    
    def test_format_mercadolivre(self):
        assert format_store_name("mercadolivre") == "Mercado Livre"
    
    def test_format_amazon(self):
        assert format_store_name("amazon") == "Amazon BR"
    
    def test_format_unknown_store(self):
        assert format_store_name("unknown") == "Unknown"
