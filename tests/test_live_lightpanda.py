"""
tests/test_live_lightpanda.py — Smoke live do Lightpanda (Inc 5).

Roda 1 scraper via Lightpanda real. Gated por env ``PRECOSBOT_LIVE=1`` (mesmo
padrão de test_live_scrapers/test_antibot) para o CI unitário não coletar.

Uso (com o binário lightpanda no PATH ou LIGHTPANDA_BIN):
    PRECOSBOT_LIVE=1 python -m pytest tests/test_live_lightpanda.py -v
"""

from __future__ import annotations

import os

import pytest

from core.browser import LightpandaBrowser
from scrapers.kabum import KabumScraper

pytestmark = pytest.mark.skipif(
    os.getenv("PRECOSBOT_LIVE") != "1",
    reason="smoke live: requer PRECOSBOT_LIVE=1 e binário lightpanda",
)


@pytest.mark.asyncio
async def test_kabum_via_lightpanda():
    """Scrapeia KaBuM via Lightpanda real e confere que retorna preço."""
    browser = LightpandaBrowser()
    await browser.start()
    try:
        scraper = KabumScraper(browser=browser, search_term="rtx-4060")
        async with scraper:
            result = await scraper.scrape()
    finally:
        await browser.stop()

    assert result is not None
    assert result.price is not None and result.price > 0
    assert result.available is True
