"""
tests/test_embeds.py — Unit tests for toolkit.py interface.

Replaces old bot/embeds tests. Validates toolkit functions return correct structure.
"""

import pytest
from unittest.mock import AsyncMock, patch

from db.repositories import PriceRecord


def _make_record(store_id="kabum", price=1500.0, available=True, scraped_at="2026-05-01 12:00:00"):
    return PriceRecord(
        store_id=store_id,
        price=price,
        available=available,
        stock_label="Em estoque" if available else "",
        url=f"https://{store_id}.com/product",
        scraped_at=scraped_at,
        product_name="RTX 4060",
        search_term="rtx-4060",
    )


class TestToolkitGetLatest:
    @pytest.mark.asyncio
    async def test_get_latest_calls_repo(self):
        records = [_make_record("kabum", 1500.0), _make_record("pichau", 1600.0)]
        with patch("toolkit.get_all_latest", new=AsyncMock(return_value=records)) as mock:
            from toolkit import get_latest
            result = await get_latest("RTX 4060")
            mock.assert_called_once_with(product_name="RTX 4060")
            assert len(result) == 2


class TestToolkitBestDeal:
    @pytest.mark.asyncio
    async def test_best_deal_returns_cheapest_available(self):
        records = [
            _make_record("kabum", 1500.0, available=True),
            _make_record("pichau", 1400.0, available=True),
            _make_record("terabyte", None, available=False),
        ]
        with patch("toolkit.get_all_latest", new=AsyncMock(return_value=records)):
            from toolkit import best_deal
            result = await best_deal("RTX 4060")
            assert result is not None
            assert result.price == 1400.0
            assert result.store_id == "pichau"

    @pytest.mark.asyncio
    async def test_best_deal_returns_none_when_no_available(self):
        records = [_make_record("kabum", None, available=False)]
        with patch("toolkit.get_all_latest", new=AsyncMock(return_value=records)):
            from toolkit import best_deal
            result = await best_deal("RTX 4060")
            assert result is None


class TestToolkitCompare:
    @pytest.mark.asyncio
    async def test_compare_returns_per_product_dict(self):
        records_a = [_make_record("kabum", 1500.0)]
        records_b = [_make_record("kabum", 2500.0)]
        side_effects = [records_a, records_b]

        async def mock_get_all_latest(**kwargs):
            return side_effects.pop(0)

        with patch("toolkit.get_all_latest", side_effect=mock_get_all_latest):
            from toolkit import compare
            result = await compare(["RTX 4060", "RTX 4070"])
            assert "RTX 4060" in result
            assert "RTX 4070" in result
            assert result["RTX 4060"][0].price == 1500.0


class TestToolkitGetAnalysis:
    @pytest.mark.asyncio
    async def test_get_analysis_structure(self):
        stats = {"min": 1400.0, "max": 1600.0, "avg": 1500.0, "n": 3}
        min_record = _make_record("kabum", 1400.0)

        with (
            patch("toolkit.get_history_stats", new=AsyncMock(return_value=stats)),
            patch("toolkit.get_historical_min", new=AsyncMock(return_value=min_record)),
        ):
            from toolkit import get_analysis
            result = await get_analysis("RTX 4060", days=30)
            assert result["product"] == "RTX 4060"
            assert result["days"] == 30
            assert "per_store" in result
            assert result["overall_min"]["price"] == 1400.0
