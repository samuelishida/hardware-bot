"""
tests/test_olx.py — Unit tests for scrapers/olx.py.

Tests pure functions that do not require a browser:
  - _build_search_url
  - _parse_olx_price
  - _extract_from_next_data / _walk
  - _pick_best
"""

import pytest
from scrapers.olx import OLXScraper


class TestBuildSearchUrl:
    def test_simple_term(self):
        scraper = OLXScraper(search_term="rtx-4060")
        url = scraper._build_search_url()
        assert url == "https://www.olx.com.br/brasil?q=rtx%204060&sf=1"

    def test_multiword_term(self):
        scraper = OLXScraper(search_term="rx-7900-xtx")
        url = scraper._build_search_url()
        assert url == "https://www.olx.com.br/brasil?q=rx%207900%20xtx&sf=1"

    def test_special_chars_removed(self):
        scraper = OLXScraper(search_term="rtx-4060-ti!")
        url = scraper._build_search_url()
        assert "rtx%204060%20ti" in url
        assert "!" not in url


class TestParseOlxPrice:
    def test_integer_price(self):
        assert OLXScraper._parse_olx_price(4400) == 4400.0

    def test_float_price(self):
        assert OLXScraper._parse_olx_price(4400.50) == 4400.5

    def test_string_with_comma(self):
        assert OLXScraper._parse_olx_price("R$ 4.400,00") == 4400.0

    def test_string_with_dot(self):
        assert OLXScraper._parse_olx_price("4400.00") == 4400.0

    def test_string_raw(self):
        assert OLXScraper._parse_olx_price("9558,00") == 9558.0

    def test_zero_returns_none(self):
        assert OLXScraper._parse_olx_price(0) is None

    def test_invalid_returns_none(self):
        assert OLXScraper._parse_olx_price("foo") is None

    def test_none_returns_none(self):
        assert OLXScraper._parse_olx_price(None) is None


class TestExtractFromNextData:
    def test_empty_dict(self):
        scraper = OLXScraper()
        assert scraper._extract_from_next_data({}) == []

    def test_flat_offer(self):
        scraper = OLXScraper()
        data = {
            "props": {
                "pageProps": {
                    "offers": [
                        {"title": "GPU RX 7900", "price": 5000, "url": "https://olx.com.br/1"},
                    ]
                }
            }
        }
        results = scraper._extract_from_next_data(data)
        assert len(results) == 1
        assert results[0]["title"] == "GPU RX 7900"
        assert results[0]["price"] == 5000.0
        assert results[0]["url"] == "https://olx.com.br/1"

    def test_nested_list_subject(self):
        scraper = OLXScraper()
        data = {
            "listings": {
                "data": [
                    {"listSubject": "RX 7900 XTX", "amount": 4400.0, "permalink": "https://olx.com.br/2"}
                ]
            }
        }
        results = scraper._extract_from_next_data(data)
        assert len(results) == 1
        assert results[0]["title"] == "RX 7900 XTX"
        assert results[0]["price"] == 4400.0

    def test_deeply_nested(self):
        scraper = OLXScraper()
        data = {
            "a": {
                "b": {
                    "c": [
                        {"title": "GPU 1", "price": 1000},
                        {"title": "GPU 2", "price": 2000},
                    ]
                }
            }
        }
        results = scraper._extract_from_next_data(data)
        assert len(results) == 2

    def test_low_price_filtered_out(self):
        scraper = OLXScraper()
        data = {
            "offers": [
                {"title": "Barato", "price": 50},   # should be filtered (<100)
                {"title": "Caro", "price": 5000},
            ]
        }
        results = scraper._extract_from_next_data(data)
        assert len(results) == 1
        assert results[0]["title"] == "Caro"


class TestPickBest:
    def test_cheapest_first(self):
        scraper = OLXScraper()
        offers = [
            {"title": "A", "price": 5000, "url": "u1"},
            {"title": "B", "price": 4000, "url": "u2"},
            {"title": "C", "price": 6000, "url": "u3"},
        ]
        result = scraper._pick_best(offers, "fallback")
        assert result.store_id == "olx"
        assert result.price == 4000.0
        assert result.url == "u2"
        assert result.available is True

    def test_no_valid_prices(self):
        scraper = OLXScraper()
        offers = [
            {"title": "A", "price": None},
            {"title": "B", "price": 50},  # filtered by _extract
        ]
        result = scraper._pick_best(offers, "fallback")
        assert result.price is None
        assert result.available is False

    def test_empty_list(self):
        scraper = OLXScraper()
        result = scraper._pick_best([], "fallback")
        assert result.price is None
        assert result.available is False
        assert result.stock_label == "Não encontrado"

    def test_no_url_fallback(self):
        scraper = OLXScraper()
        offers = [{"title": "X", "price": 3000}]
        result = scraper._pick_best(offers, "https://fallback.url")
        assert result.url == "https://fallback.url"
