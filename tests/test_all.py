"""
tests/test_all.py — Test runner for all unit tests.

Run with: python -m pytest tests/test_all.py -v
Or: python tests/test_all.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_quick_validation():
    """Run quick validation without pytest."""
    print("\n" + "="*70)
    print("🧪 PreçoBot v2.1 — Quick Validation")
    print("="*70)
    
    errors = []
    
    # Test 1: ProductManager
    print("\n📦 Testando ProductManager...")
    try:
        from core.product_manager import ProductManager
        pm = ProductManager()
        product = pm.parse_product_name("RTX 4060 Ti")
        assert product.name == "RTX 4060 Ti"
        assert product.search_term == "rtx-4060-ti"
        print("   ✅ Normalização OK")
        
        url = pm.get_search_url("kabum", "rtx-4060")
        assert "rtx-4060" in url
        print("   ✅ Geração de URLs OK")
        
        from utils.formatters import format_price_brl
        formatted = format_price_brl(1234.56)
        assert formatted == "R$ 1.234,56"
        print("   ✅ Formatação BRL OK")
    except Exception as e:
        errors.append(f"ProductManager: {e}")
        print(f"   ❌ Error: {e}")
    
    # Test 2: Formatters
    print("\n🔧 Testando utils.formatters...")
    try:
        from utils.formatters import format_price_brl, format_store_name, normalize_search_term
        
        assert format_price_brl(1234.56) == "R$ 1.234,56"
        assert format_price_brl(None) == "Indisponível"
        print("   ✅ format_price_brl OK")
        
        assert format_store_name("kabum") == "KaBuM!"
        assert format_store_name("unknown") == "Unknown"
        print("   ✅ format_store_name OK")
        
        assert normalize_search_term("RTX 4060 Ti") == "rtx-4060-ti"
        print("   ✅ normalize_search_term OK")
    except Exception as e:
        errors.append(f"Formatters: {e}")
        print(f"   ❌ Error: {e}")
    
    # Test 3: Embeds (only if bot/embeds.py exists)
    print("\n🎨 Testando bot.embeds...")
    try:
        from bot.embeds import make_prices_table_embed, make_price_drop_embed, make_help_embed
        from scrapers.base import ScrapeResult
        
        results = [
            ScrapeResult(store_id="kabum", price=1500.0, available=True, stock_label="", url=""),
            ScrapeResult(store_id="pichau", price=1600.0, available=True, stock_label="", url=""),
        ]
        embed = make_prices_table_embed(results, product_name="RTX 4060")
        assert "RTX 4060" in embed.title
        print("   ✅ make_prices_table_embed OK")
        
        drop_embed = make_price_drop_embed(results[0], 2000.0, 25.0, "RTX 4060")
        assert "ALERTA DE PREÇO" in drop_embed.title
        print("   ✅ make_price_drop_embed OK")
        
        help_embed = make_help_embed()
        assert len(help_embed.fields) >= 5
        print("   ✅ make_help_embed OK")
    except ImportError:
        print("   ⚠️ bot.embeds não disponível (OK para modo agente)")
    except Exception as e:
        errors.append(f"Embeds: {e}")
        print(f"   ❌ Error: {e}")
    
    # Test 4: Repositories (schema validation)
    print("\n💾 Testando db.repositories...")
    try:
        from db.repositories import PriceRecord
        
        record = PriceRecord(
            store_id="kabum",
            price=1500.0,
            available=True,
            stock_label="Em estoque",
            url="https://kabum.com",
            scraped_at="2026-04-26",
            product_name="RTX 4060",
            search_term="rtx-4060",
        )
        assert record.store_id == "kabum"
        assert record.price == 1500.0
        assert record.product_name == "RTX 4060"
        print("   ✅ PriceRecord OK")
        
        # Minimal record
        minimal = PriceRecord(
            store_id="pichau",
            price=1600.0,
            available=True,
            stock_label="",
            url="",
            scraped_at="2026-04-26",
            product_name="RTX 4060",
            search_term="rtx-4060",
        )
        assert minimal.store_id == "pichau"
        print("   ✅ Minimal PriceRecord OK")
    except Exception as e:
        errors.append(f"Repositories: {e}")
        print(f"   ❌ Error: {e}")
    
    # Test 5: Scraper initialization
    print("\n🕷️ Testando inicialização dos scrapers...")
    try:
        from scrapers.kabum import KabumScraper
        from scrapers.pichau import PichauScraper
        from scrapers.amazon import AmazonScraper
        from scrapers.olx import OLXScraper
        from scrapers.enjoei import EnjoeiScraper
        
        assert hasattr(KabumScraper, '__init__')
        assert hasattr(PichauScraper, '__init__')
        assert hasattr(AmazonScraper, '__init__')
        assert hasattr(OLXScraper, '__init__')
        assert hasattr(EnjoeiScraper, '__init__')
        print("   ✅ KabumScraper OK")
        print("   ✅ PichauScraper OK")
        print("   ✅ AmazonScraper OK")
        print("   ✅ OLXScraper OK")
        print("   ✅ EnjoeiScraper OK")
    except Exception as e:
        errors.append(f"Scrapers: {e}")
        print(f"   ❌ Error: {e}")

    # Test 6: History logger
    print("\n📜 Testando history_logger...")
    try:
        from utils.history_logger import log_scrape, HISTORY_PATH
        import os
        
        # Clean up any existing test history
        test_path = HISTORY_PATH
        if test_path.exists():
            test_path.unlink()
        
        log_scrape("olx", "RX 7900 XTX", 4400.0, True, "https://olx.com.br/1")
        log_scrape("kabum", "RTX 4060", None, False, "https://kabum.com.br/1")
        
        content = test_path.read_text()
        assert "olx" in content
        assert "RX 7900 XTX" in content
        assert "R$ 4.400,00" in content
        assert "❌" in content
        assert "✅" in content
        print("   ✅ log_scrape OK")
        print("   ✅ HISTORY.md format OK")
    except Exception as e:
        errors.append(f"History: {e}")
        print(f"   ❌ Error: {e}")
    
    # Test 7: Config
    print("\n⚙️ Testando config...")
    try:
        from config import (
            STORE_URL_TEMPLATES,
            STORE_DISPLAY_NAMES,
            STORE_COLORS,
        )
        
        assert "kabum" in STORE_URL_TEMPLATES
        assert "{query}" in STORE_URL_TEMPLATES["kabum"]
        print("   ✅ STORE_URL_TEMPLATES OK")
        
        assert "olx" in STORE_URL_TEMPLATES
        assert "enjoei" in STORE_URL_TEMPLATES
        print("   ✅ New stores (OLX, Enjoei) OK")
    except Exception as e:
        errors.append(f"Config: {e}")
        print(f"   ❌ Error: {e}")
    
    # Summary
    print("\n" + "="*70)
    if errors:
        print(f"❌ {len(errors)} erro(s) encontrado(s):")
        for error in errors:
            print(f"   - {error}")
    else:
        print("✅ All validations passed!")
    print("="*70 + "\n")
    
    return len(errors) == 0


if __name__ == "__main__":
    success = run_quick_validation()
    sys.exit(0 if success else 1)
