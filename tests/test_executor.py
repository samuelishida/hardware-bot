"""
tests/test_executor.py — Unit tests for core/executor.py.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.executor import scrape_product
from scrapers.base import ScrapeResult


class TestScrapeProduct:
    async def test_scrape_product_filters_none_results(self):
        """scrape_product returns only non-None results."""
        good = ScrapeResult(store_id="kabum", price=1500.0, available=True, stock_label="", url="")

        class GoodScraper:
            store_id = "kabum"
            def __init__(self, browser=None, search_term=None): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def scrape(self): return good

        class BadScraper:
            store_id = "bad"
            def __init__(self, browser=None, search_term=None): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def scrape(self): raise Exception("fail")

        with patch("core.executor.async_playwright") as mock_pw:
            mock_browser = AsyncMock()
            ctx_mgr = AsyncMock()
            ctx_mgr.__aenter__ = AsyncMock(return_value=ctx_mgr)
            ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            ctx_mgr.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_pw.return_value = ctx_mgr

            results = await scrape_product(
                [GoodScraper, BadScraper, GoodScraper],
                [],
                "test-term",
            )

            assert len(results) == 2
            assert all(r is not None for r in results)

    async def test_scrape_product_sequential_order(self):
        """All scraper classes run in order: browser first, then http."""
        calls = []

        class FakeBase:
            def __init__(self, browser=None, search_term=None):
                calls.append(type(self).store_id)
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def scrape(self): return None

        class A(FakeBase): store_id = "browser1"
        class B(FakeBase): store_id = "browser2"
        class C(FakeBase): store_id = "http1"

        with patch("core.executor.async_playwright") as mock_pw:
            mock_browser = AsyncMock()
            ctx_mgr = AsyncMock()
            ctx_mgr.__aenter__ = AsyncMock(return_value=ctx_mgr)
            ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            ctx_mgr.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_pw.return_value = ctx_mgr

            await scrape_product([A, B], [C], "test")

        assert calls == ["browser1", "browser2", "http1"]

    async def test_scrape_product_timeout(self):
        """A scraper that exceeds the timeout is skipped."""

        class SlowScraper:
            store_id = "slow"
            def __init__(self, browser=None, search_term=None): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def scrape(self):
                await asyncio.sleep(999)

        with patch("core.executor.async_playwright") as mock_pw:
            mock_browser = AsyncMock()
            ctx_mgr = AsyncMock()
            ctx_mgr.__aenter__ = AsyncMock(return_value=ctx_mgr)
            ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            ctx_mgr.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_pw.return_value = ctx_mgr

            with patch("core.executor.SCRAPER_TIMEOUT", 0.1):
                results = await scrape_product([SlowScraper], [], "test")

        assert len(results) == 0
