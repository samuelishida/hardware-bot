"""
tests/test_integration.py — Integration tests for PreçoBot agentic toolkit.
"""

import pytest
from core.product_manager import ProductManager
from scrapers.base import ScrapeResult
from db.repositories import PriceRecord


class TestProductManagerIntegration:
    def test_full_product_parse_flow(self):
        pm = ProductManager()
        product = pm.parse_product_name("RTX 4060 Ti")
        assert product.name == "RTX 4060 Ti"
        assert product.search_term == "rtx-4060-ti"

        for store_id in ["kabum", "pichau", "terabyte", "amazon"]:
            url = pm.get_search_url(store_id, product.search_term)
            assert product.search_term in url

    def test_price_formatting_consistency(self):
        from utils.formatters import format_price_brl
        for price in [0, 0.99, 10.00, 100.00, 1000.00, 10000.00]:
            formatted = format_price_brl(price)
            assert "R$" in formatted
            assert "," in formatted


class TestDataFlowIntegration:
    def test_price_record_creation(self):
        scrape_result = ScrapeResult(
            store_id="kabum",
            price=1599.99,
            available=True,
            stock_label="Em estoque",
            url="https://kabum.com/product",
        )
        price_record = PriceRecord(
            store_id=scrape_result.store_id,
            price=scrape_result.price,
            available=scrape_result.available,
            stock_label=scrape_result.stock_label,
            url=scrape_result.url,
            scraped_at="2026-05-01 12:00:00",
            product_name="RTX 4060 Ti",
            search_term="rtx-4060-ti",
        )
        assert price_record.store_id == "kabum"
        assert price_record.price == 1599.99
        assert price_record.product_name == "RTX 4060 Ti"

    def test_price_record_defaults_are_empty(self):
        record = PriceRecord(
            store_id="kabum",
            price=1500.0,
            available=True,
            stock_label="",
            url="",
            scraped_at="2026-05-01",
        )
        assert record.product_name == ""
        assert record.search_term == ""
