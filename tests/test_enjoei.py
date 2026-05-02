"""
tests/test_enjoei.py — Unit tests for scrapers/enjoei.py.

Tests pure functions that do not require a browser:
  - _build_search_url
  - _pick_best
"""

import pytest
from scrapers.enjoei import EnjoeiScraper


class TestBuildSearchUrl:
    def test_simple_term(self):
        scraper = EnjoeiScraper(search_term="rtx-4060")
        url = scraper._build_search_url()
        assert url == "https://www.enjoei.com.br/busca?term=rtx%204060"

    def test_multiword_term(self):
        scraper = EnjoeiScraper(search_term="rx-7900-xtx")
        url = scraper._build_search_url()
        assert url == "https://www.enjoei.com.br/busca?term=rx%207900%20xtx"

    def test_special_chars_removed(self):
        scraper = EnjoeiScraper(search_term="rtx-4060-ti!")
        url = scraper._build_search_url()
        assert "rtx%204060%20ti" in url
        assert "!" not in url


class TestPickBest:
    def test_cheapest_first(self):
        scraper = EnjoeiScraper()
        offers = [
            {"title": "A", "price": 5000, "url": "u1"},
            {"title": "B", "price": 3500, "url": "u2"},
            {"title": "C", "price": 6000, "url": "u3"},
        ]
        result = scraper._pick_best(offers, "fallback")
        assert result.store_id == "enjoei"
        assert result.price == 3500.0
        assert result.url == "u2"
        assert result.available is True
        assert result.stock_label == "Em estoque"

    def test_low_price_threshold(self):
        scraper = EnjoeiScraper()
        offers = [
            {"title": "A", "price": 30},   # < 50 threshold
            {"title": "B", "price": 100},
        ]
        result = scraper._pick_best(offers, "fallback")
        # Only B is valid
        assert result.price == 100.0

    def test_no_valid_prices(self):
        scraper = EnjoeiScraper()
        offers = [
            {"title": "A", "price": None},
            {"title": "B", "price": 10},  # < 50 threshold
        ]
        result = scraper._pick_best(offers, "fallback")
        assert result.price is None
        assert result.available is False
        assert result.stock_label == "Esgotado / Sem preço"

    def test_empty_list(self):
        scraper = EnjoeiScraper()
        result = scraper._pick_best([], "fallback")
        assert result.price is None
        assert result.available is False
        assert result.stock_label == "Não encontrado"

    def test_no_url_fallback(self):
        scraper = EnjoeiScraper()
        offers = [{"title": "X", "price": 250}]
        result = scraper._pick_best(offers, "https://fallback.url")
        assert result.url == "https://fallback.url"
