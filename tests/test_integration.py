"""
tests/test_integration.py — Integration tests for PreçoBot v2.1.

Tests the full pipeline: ProductManager → Scrapers → Database → Embeds.
"""

import pytest
from core.product_manager import ProductManager
from scrapers.base import ScrapeResult
from bot.embeds import make_prices_table_embed, make_price_drop_embed
from db.repositories import PriceRecord


class TestProductManagerIntegration:
    """Integration tests for ProductManager."""
    
    def test_full_product_parse_flow(self):
        """Test complete product parsing and URL generation flow."""
        pm = ProductManager()
        
        # Parse product name
        product = pm.parse_product_name("RTX 4060 Ti")
        assert product.name == "RTX 4060 Ti"
        assert product.search_term == "rtx-4060-ti"
        
        # Generate URLs for all stores
        for store_id in ["kabum", "pichau", "terabyte", "amazon", "mercadolivre"]:
            url = pm.get_search_url(store_id, product.search_term)
            assert product.search_term in url
            assert store_id in url or pm.get_store_display_names()[store_id] in url
    
    def test_price_formatting_consistency(self):
        """Test that price formatting is consistent across modules."""
        pm = ProductManager()
        
        # Test various price points
        test_prices = [0, 0.99, 10.00, 100.00, 1000.00, 10000.00]
        for price in test_prices:
            formatted = pm.format_price_brl(price)
            assert "R$" in formatted
            assert "," in formatted  # Brazilian decimal separator


class TestEmbedIntegration:
    """Integration tests for embed generation."""
    
    def test_embed_with_real_data(self):
        """Test embed generation with realistic data."""
        results = [
            ScrapeResult(store_id="kabum", price=1599.99, available=True, stock_label="Em estoque", url="https://kabum.com/1"),
            ScrapeResult(store_id="pichau", price=1649.00, available=True, stock_label="", url="https://pichau.com/1"),
            ScrapeResult(store_id="terabyte", price=None, available=False, stock_label="", url="https://terabyte.com/1"),
            ScrapeResult(store_id="mercadolivre", price=1700.00, available=True, stock_label="Full", url="https://ml.com/1"),
            ScrapeResult(store_id="amazon", price=1699.00, available=True, stock_label="", url="https://amazon.com/1"),
        ]
        
        embed = make_prices_table_embed(results, product_name="RTX 4060 Ti")
        
        # Verify embed structure
        assert "RTX 4060 Ti" in embed.title
        assert len(embed.fields) == 5
        
        # Verify lowest price is highlighted (Kabum at 1599.99)
        kabum_field = next((f for f in embed.fields if "KaBuM" in f.name), None)
        assert kabum_field is not None
        assert "⭐" in kabum_field.value
    
    def test_price_drop_embed_calculation(self):
        """Test price drop embed with correct percentage calculation."""
        result = ScrapeResult(store_id="kabum", price=1500.0, available=True, stock_label="", url="")
        
        previous_price = 2000.0
        expected_drop_pct = 25.0  # (2000 - 1500) / 2000 * 100
        
        embed = make_price_drop_embed(result, previous_price, expected_drop_pct, product_name="RTX 4060")
        
        assert "25.0%" in embed.description
        assert "R$ 500,00" in embed.description  # Difference


class TestDataFlowIntegration:
    """Integration tests for data flow through the system."""
    
    def test_price_record_creation(self):
        """Test creating PriceRecord from ScrapeResult."""
        scrape_result = ScrapeResult(
            store_id="kabum",
            price=1599.99,
            available=True,
            stock_label="Em estoque",
            url="https://kabum.com/product",
        )
        
        # Simulate conversion to PriceRecord (what happens in jobs.py)
        price_record = PriceRecord(
            store_id=scrape_result.store_id,
            price=scrape_result.price,
            available=scrape_result.available,
            stock_label=scrape_result.stock_label,
            url=scrape_result.url,
            scraped_at="2026-04-26 12:00:00",
            product_name="RTX 4060 Ti",
            search_term="rtx-4060-ti",
        )
        
        assert price_record.store_id == "kabum"
        assert price_record.price == 1599.99
        assert price_record.product_name == "RTX 4060 Ti"


class TestBackwardCompatibility:
    """Tests for backward compatibility with v2.0."""
    
    def test_default_product_still_works(self):
        """Test that default product (5700X3D) still works."""
        pm = ProductManager()
        
        # Default product should still be supported
        product = pm.parse_product_name("AMD Ryzen 5 5700X3D")
        assert product.name == "AMD Ryzen 5 5700X3D"
        assert "5700x3d" in product.search_term
    
    def test_legacy_queries_work(self):
        """Test that legacy queries without product_name still work."""
        # PriceRecord should have defaults
        record = PriceRecord(
            store_id="kabum",
            price=1500.0,
            available=True,
            stock_label="",
            url="",
            scraped_at="2026-04-26",
        )
        
        assert record.product_name == "AMD Ryzen 5 5700X3D"
        assert record.search_term == "ryzen-5-5700x3d"


def test_quick_validation():
    """Quick validation script for manual testing."""
    print("\n" + "="*60)
    print("🧪 PreçoBot v2.1 — Quick Validation")
    print("="*60)
    
    # Test ProductManager
    pm = ProductManager()
    product = pm.parse_product_name("RTX 4060 Ti")
    print(f"✅ Product parsing: {product.name} → {product.search_term}")
    
    # Test formatters
    from utils.formatters import format_price_brl
    print(f"✅ Price formatting: {format_price_brl(1234.56)}")
    
    # Test embeds
    results = [
        ScrapeResult(store_id="kabum", price=1500.0, available=True, stock_label="", url=""),
    ]
    embed = make_prices_table_embed(results, product_name="Test")
    print(f"✅ Embed generation: {embed.title}")
    
    print("="*60)
    print("✅ All validations passed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    test_quick_validation()
