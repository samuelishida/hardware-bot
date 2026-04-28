"""
tests/test_embeds.py — Unit tests for bot/embeds.py.

Tests verify that embed factories create valid Discord embeds with correct structure.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

import discord

from bot.embeds import (
    make_price_drop_embed,
    make_restock_embed,
    make_user_alert_embed,
    make_prices_table_embed,
    make_history_embed,
    make_search_results_embed,
    make_tracking_list_embed,
    make_help_embed,
)
from scrapers.base import ScrapeResult


# Mock ScrapeResult for tests
def create_mock_result(store_id="kabum", price=1500.0, available=True):
    return ScrapeResult(
        store_id=store_id,
        price=price,
        available=available,
        stock_label="Em estoque" if available else "",
        url="https://example.com/product",
    )


class TestMakePriceDropEmbed:
    """Tests for make_price_drop_embed function."""
    
    def test_price_drop_embed_structure(self):
        """Test that price drop embed has correct structure."""
        result = create_mock_result()
        embed = make_price_drop_embed(result, previous_price=2000.0, drop_pct=25.0, product_name="RTX 4060")
        
        assert isinstance(embed, discord.Embed)
        assert "ALERTA DE PREÇO" in embed.title
        assert "RTX 4060" in embed.title
        assert embed.color == discord.Color.red()
    
    def test_price_drop_embed_fields(self):
        """Test that price drop embed has correct fields."""
        result = create_mock_result()
        embed = make_price_drop_embed(result, 2000.0, 25.0, "RTX 4060")
        
        # Should have at least 4 fields
        assert len(embed.fields) >= 4
        
        # Check for price field
        price_field = next((f for f in embed.fields if "Preço" in f.name), None)
        assert price_field is not None


class TestMakeRestockEmbed:
    """Tests for make_restock_embed function."""
    
    def test_restock_embed_structure(self):
        """Test that restock embed has correct structure."""
        result = create_mock_result()
        embed = make_restock_embed(result, product_name="RTX 4060")
        
        assert isinstance(embed, discord.Embed)
        assert "RESTOQUE" in embed.title
        assert "RTX 4060" in embed.title
        assert embed.color == discord.Color.yellow()


class TestMakeUserAlertEmbed:
    """Tests for make_user_alert_embed function."""
    
    def test_user_alert_embed_structure(self):
        """Test that user alert embed has correct structure."""
        result = create_mock_result()
        embed = make_user_alert_embed(result, target_price=1600.0, product_name="RTX 4060")
        
        assert isinstance(embed, discord.Embed)
        assert "alerta" in embed.title.lower()
        assert embed.color == discord.Color.green()


class TestMakePricesTableEmbed:
    """Tests for make_prices_table_embed function."""
    
    def test_prices_table_embed_structure(self):
        """Test that prices table embed has correct structure."""
        results = [
            create_mock_result("kabum", 1500.0),
            create_mock_result("pichau", 1600.0),
        ]
        embed = make_prices_table_embed(results, product_name="RTX 4060")
        
        assert isinstance(embed, discord.Embed)
        assert "Preços" in embed.title
        assert "RTX 4060" in embed.title
        
        # Should have a field for each store
        assert len(embed.fields) == 2
    
    def test_prices_table_embed_highlights_lowest(self):
        """Test that prices table embed highlights lowest price."""
        results = [
            create_mock_result("kabum", 1500.0),
            create_mock_result("pichau", 1600.0),
        ]
        embed = make_prices_table_embed(results, product_name="RTX 4060")
        
        # Kabum field should have star emoji
        kabum_field = next((f for f in embed.fields if "KaBuM" in f.name), None)
        assert kabum_field is not None
        assert "⭐" in kabum_field.value


class TestMakeHistoryEmbed:
    """Tests for make_history_embed function."""
    
    def test_history_embed_structure(self):
        """Test that history embed has correct structure."""
        embed = make_history_embed(
            store_id="kabum",
            min_price=1400.0,
            max_price=2000.0,
            avg_price=1700.0,
            days=30,
            product_name="RTX 4060",
        )
        
        assert isinstance(embed, discord.Embed)
        assert "Histórico" in embed.title
        
        # Check for min/max/avg fields
        field_names = [f.name for f in embed.fields]
        assert "📉 Mínimo" in field_names
        assert "📈 Máximo" in field_names
        assert "⚖️ Média" in field_names


class TestMakeSearchResultsEmbed:
    """Tests for make_search_results_embed function."""
    
    def test_search_results_embed_structure(self):
        """Test that search results embed has correct structure."""
        results = [
            create_mock_result("kabum", 1500.0),
            create_mock_result("pichau", 1600.0),
        ]
        embed = make_search_results_embed(results, product_name="RTX 4060")
        
        assert isinstance(embed, discord.Embed)
        assert "🔍" in embed.title
        assert "RTX 4060" in embed.title


class TestMakeTrackingListEmbed:
    """Tests for make_tracking_list_embed function."""
    
    def test_tracking_list_embed_structure(self):
        """Test that tracking list embed has correct structure."""
        products = ["RTX 4060", "RTX 4070", "iPhone 15"]
        embed = make_tracking_list_embed(channel_id="123456", products=products)
        
        assert isinstance(embed, discord.Embed)
        assert "Produtos Monitorados" in embed.title
        assert len(products) == 3


class TestMakeHelpEmbed:
    """Tests for make_help_embed function."""
    
    def test_help_embed_structure(self):
        """Test that help embed has correct structure."""
        embed = make_help_embed()
        
        assert isinstance(embed, discord.Embed)
        assert "Comandos" in embed.title
        assert embed.color == discord.Color.blurple()
        
        # Should have multiple command fields
        assert len(embed.fields) >= 5
