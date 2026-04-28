"""
tests/test_executor.py — Unit tests for scheduler/executor.py.

Note: These tests mock the actual scrapers since we don't want to make
real HTTP requests or launch browsers during unit tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from scheduler.executor import (
    run_scraper,
    execute_browser_scrapers,
    execute_http_scrapers,
    scrape_product,
)
from scrapers.base import ScrapeResult


class TestRunScraper:
    """Tests for run_scraper function."""
    
    @pytest.mark.asyncio
    async def test_run_scraper_success(self):
        """Test successful scraper execution."""
        mock_scraper = AsyncMock()
        mock_scraper.__aenter__ = AsyncMock(return_value=mock_scraper)
        mock_scraper.__aexit__ = AsyncMock(return_value=None)
        mock_scraper.scrape = AsyncMock(return_value=ScrapeResult(
            store_id="kabum",
            price=1500.00,
            available=True,
            stock_label="Em estoque",
            url="https://kabum.com.br/product",
        ))
        
        result = await run_scraper(lambda: mock_scraper)
        
        assert result is not None
        assert result.price == 1500.00
        assert result.store_id == "kabum"
    
    @pytest.mark.asyncio
    async def test_run_scraper_failure(self):
        """Test scraper that raises an exception."""
        mock_scraper = AsyncMock()
        mock_scraper.__aenter__ = AsyncMock(return_value=mock_scraper)
        mock_scraper.__aexit__ = AsyncMock(return_value=None)
        mock_scraper.scrape = AsyncMock(side_effect=Exception("Test error"))
        
        result = await run_scraper(lambda: mock_scraper)
        
        assert result is None


class TestExecuteBrowserScrapers:
    """Tests for execute_browser_scrapers function."""
    
    @pytest.mark.asyncio
    async def test_execute_multiple_browser_scrapers(self):
        """Test executing multiple browser scrapers in parallel."""
        mock_browser = MagicMock()
        
        # Create mock scrapers
        def create_mock_scraper(price):
            mock = AsyncMock()
            mock.__aenter__ = AsyncMock(return_value=mock)
            mock.__aexit__ = AsyncMock(return_value=None)
            mock.scrape = AsyncMock(return_value=ScrapeResult(
                store_id=f"store{price}",
                price=price,
                available=True,
                stock_label="",
                url="",
            ))
            return mock
        
        with patch('scheduler.executor.run_scraper') as mock_run:
            mock_run.side_effect = [
                ScrapeResult(store_id="store1", price=100.0, available=True, stock_label="", url=""),
                ScrapeResult(store_id="store2", price=200.0, available=True, stock_label="", url=""),
            ]
            
            results = await execute_browser_scrapers(
                mock_browser,
                [MagicMock(), MagicMock()],
                "test-term",
            )
            
            assert len(results) == 2


class TestExecuteHttpScrapers:
    """Tests for execute_http_scrapers function."""
    
    @pytest.mark.asyncio
    async def test_execute_multiple_http_scrapers(self):
        """Test executing multiple HTTP scrapers in parallel."""
        with patch('scheduler.executor.run_scraper') as mock_run:
            mock_run.side_effect = [
                ScrapeResult(store_id="ml", price=150.0, available=True, stock_label="", url=""),
            ]
            
            results = await execute_http_scrapers(
                [MagicMock()],
                "test-term",
            )
            
            assert len(results) == 1


class TestScrapeProduct:
    """Tests for scrape_product function."""
    
    @pytest.mark.asyncio
    async def test_scrape_product_filters_none_results(self):
        """Test that scrape_product filters out None results."""
        with patch('scheduler.executor.async_playwright') as mock_pw:
            mock_browser = AsyncMock()
            mock_pw.return_value.__aenter__.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)
            
            with patch('scheduler.executor.execute_browser_scrapers') as mock_browser_exec:
                mock_browser_exec.return_value = [
                    ScrapeResult(store_id="kabum", price=1500.0, available=True, stock_label="", url=""),
                    None,  # Simulate failure
                ]
                
                with patch('scheduler.executor.execute_http_scrapers') as mock_http_exec:
                    mock_http_exec.return_value = [
                        ScrapeResult(store_id="ml", price=1600.0, available=True, stock_label="", url=""),
                    ]
                    
                    results = await scrape_product(
                        [MagicMock(), MagicMock()],
                        [MagicMock()],
                        "test-term",
                    )
                    
                    # Should filter out the None result
                    assert len(results) == 2
                    assert all(r is not None for r in results)
