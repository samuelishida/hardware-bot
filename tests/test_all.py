"""
tests/test_all.py — Quick validation runner (no pytest required).

Run with: python tests/test_all.py
Or:       python -m pytest tests/test_all.py -v
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_quick_validation():
    print("\n" + "="*70)
    print("PrecoBot — Quick Validation")
    print("="*70)

    errors = []

    # Test 1: ProductManager
    print("\nTestando ProductManager...")
    try:
        from core.product_manager import ProductManager
        pm = ProductManager()
        product = pm.parse_product_name("RTX 4060 Ti")
        assert product.name == "RTX 4060 Ti"
        assert product.search_term == "rtx-4060-ti"
        print("   OK Normalizacao")

        url = pm.get_search_url("kabum", "rtx-4060")
        assert "rtx-4060" in url
        print("   OK Geracao de URLs")

        from utils.formatters import format_price_brl
        assert format_price_brl(1234.56) == "R$ 1.234,56"
        print("   OK Formatacao BRL")
    except Exception as e:
        errors.append(f"ProductManager: {e}")
        print(f"   FALHA: {e}")

    # Test 2: Formatters
    print("\nTestando utils.formatters...")
    try:
        from utils.formatters import format_price_brl, format_store_name, normalize_search_term
        assert format_price_brl(1234.56) == "R$ 1.234,56"
        assert format_price_brl(None) == "Indisponível"
        print("   OK format_price_brl")

        assert format_store_name("kabum") == "KaBuM!"
        assert format_store_name("unknown") == "Unknown"
        print("   OK format_store_name")

        assert normalize_search_term("RTX 4060 Ti") == "rtx-4060-ti"
        print("   OK normalize_search_term")
    except Exception as e:
        errors.append(f"Formatters: {e}")
        print(f"   FALHA: {e}")

    # Test 3: PriceRecord schema
    print("\nTestando db.repositories...")
    try:
        from db.repositories import PriceRecord
        record = PriceRecord(
            store_id="kabum",
            price=1500.0,
            available=True,
            stock_label="Em estoque",
            url="https://kabum.com",
            scraped_at="2026-05-01",
            product_name="RTX 4060",
            search_term="rtx-4060",
        )
        assert record.store_id == "kabum"
        assert record.price == 1500.0
        print("   OK PriceRecord")

        # Defaults are empty strings
        legacy = PriceRecord(store_id="kabum", price=1500.0, available=True,
                             stock_label="", url="", scraped_at="2026-05-01")
        assert legacy.product_name == ""
        print("   OK defaults are empty strings")
    except Exception as e:
        errors.append(f"Repositories: {e}")
        print(f"   FALHA: {e}")

    # Test 4: Toolkit imports
    print("\nTestando toolkit...")
    try:
        import toolkit
        assert callable(toolkit.scrape)
        assert callable(toolkit.scrape_and_store)
        assert callable(toolkit.get_latest)
        assert callable(toolkit.get_history)
        assert callable(toolkit.best_deal)
        assert callable(toolkit.compare)
        assert callable(toolkit.get_analysis)
        print("   OK all toolkit functions importable")
    except Exception as e:
        errors.append(f"Toolkit: {e}")
        print(f"   FALHA: {e}")

    # Test 5: Scraper init
    print("\nTestando scrapers...")
    try:
        from scrapers.kabum import KabumScraper
        from scrapers.pichau import PichauScraper
        from scrapers.amazon import AmazonScraper
        assert hasattr(KabumScraper, '__init__')
        assert hasattr(PichauScraper, '__init__')
        assert hasattr(AmazonScraper, '__init__')
        print("   OK KabumScraper, PichauScraper, AmazonScraper")
    except Exception as e:
        errors.append(f"Scrapers: {e}")
        print(f"   FALHA: {e}")

    # Test 6: Config
    print("\nTestando config...")
    try:
        from config import STORE_URL_TEMPLATES, STORE_DISPLAY_NAMES, STORE_COLORS, ALL_STORE_IDS
        assert "kabum" in STORE_URL_TEMPLATES
        assert "{query}" in STORE_URL_TEMPLATES["kabum"]
        assert len(ALL_STORE_IDS) >= 5
        print("   OK STORE_URL_TEMPLATES, STORE_DISPLAY_NAMES, STORE_COLORS, ALL_STORE_IDS")
    except Exception as e:
        errors.append(f"Config: {e}")
        print(f"   FALHA: {e}")

    print("\n" + "="*70)
    if errors:
        print(f"FALHA — {len(errors)} erro(s):")
        for error in errors:
            print(f"   - {error}")
    else:
        print("OK — all validations passed!")
    print("="*70 + "\n")

    return len(errors) == 0


if __name__ == "__main__":
    success = run_quick_validation()
    sys.exit(0 if success else 1)
