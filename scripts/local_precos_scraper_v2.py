#!/usr/bin/env python3
"""
local_precos_scraper.py - Script para rodar LOCAL (IP residencial brasileiro).

LEGADO (Inc 4 Lightpanda): este script usa Playwright diretamente e roda apenas
em dev local (Windows/Linux/Mac com IP residencial). NÃO está no caminho de runtime
do precosbot (executor + scrapers usam a facade Lightpanda). Para dev local com
Lightpanda, use WSL2 (sem binário Windows). Fora de escopo da migração.

Roda em qualquer PC Windows/Linux/Mac com IP de casa para evitar cloud block.
Coleta precos de RAM DDR4/DDR5 via Playwright + PrecoBot.
Exporta os dados em JSON para sincronizar com a VM na OCI depois.

Instalacao:
    cd precosbot
    python -m venv venv
    venv\Scripts\pip install -r requirements.txt    # Windows
    venv/bin/pip install -r requirements.txt       # Linux/Mac
    playwright install chromium

Uso:
    python scripts/local_precos_scraper.py              # Coleta tudo
    python scripts/local_precos_scraper.py --upload     # Coleta + sobe JSON pro servidor
"""
from __future__ import annotations
import asyncio
import argparse
import json
import os
import subprocess
import sys
import io
from datetime import datetime
from pathlib import Path

# Force UTF-8 on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Adiciona o diretorio do repo ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from playwright.async_api import async_playwright
    from scrapers.kabum import KabumScraper
    from scrapers.pichau import PichauScraper
    from scrapers.amazon import AmazonScraper
    from scrapers.base import ScrapeResult
except ImportError as e:
    print(f"Erro de importacao: {e}")
    print("Verifique se esta no diretorio do precosbot e se o venv esta ativado.")
    sys.exit(1)


PRODUCTS = [
    ("memoria ddr4 8gb 3200mhz", "DDR4 8GB 3200MHz"),
    ("memoria ddr4 16gb 3200mhz", "DDR4 16GB 3200MHz"),
    ("memoria ddr4 16gb 3600mhz", "DDR4 16GB 3600MHz"),
    ("memoria ddr4 32gb 3200mhz", "DDR4 32GB 3200MHz"),
    ("memoria ddr5 16gb 4800mhz", "DDR5 16GB 4800MHz"),
    ("memoria ddr5 16gb 5600mhz", "DDR5 16GB 5600MHz"),
    ("memoria ddr5 32gb 5600mhz", "DDR5 32GB 5600MHz"),
    ("memoria ddr5 32gb 6000mhz", "DDR5 32GB 6000MHz"),
]

OUTPUT_DIR = Path(__file__).parent / "local_exports"
OUTPUT_DIR.mkdir(exist_ok=True)

SCRAPER_TIMEOUT = 60

STEALTH_ARGS = [
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-default-apps",
    "--disable-hang-monitor",
    "--disable-popup-blocking",
    "--disable-renderer-backgrounding",
    "--disable-blink-features=AutomationControlled",
    "--window-size=1920,1080",
]


async def scrape_one(browser, scraper_cls, search_term: str) -> ScrapeResult | None:
    store_id = getattr(scraper_cls, 'store_id', scraper_cls.__name__)
    try:
        scraper = scraper_cls(browser=browser, search_term=search_term)
        async with scraper:
            result = await asyncio.wait_for(scraper.scrape(), timeout=SCRAPER_TIMEOUT)
            return result
    except asyncio.TimeoutError:
        print(f"  [{store_id}] TIMEOUT apos {SCRAPER_TIMEOUT}s")
        return None
    except Exception as e:
        print(f"  [{store_id}] ERRO: {e}")
        return None


async def collect_all():
    """Coleta precos de todos os produtos."""
    results = {}
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
        
        for search_term, display_name in PRODUCTS:
            print(f"\n[PRODUTO] {display_name}")
            prices = []
            
            for scraper_cls in [KabumScraper, PichauScraper, AmazonScraper]:
                store_id = getattr(scraper_cls, 'store_id', scraper_cls.__name__)
                print(f"  -> {store_id}...", end=" ", flush=True)
                result = await scrape_one(browser, scraper_cls, search_term)
                if result and result.price is not None:
                    prices.append({
                        "store": result.store_id,
                        "price": result.price,
                        "available": result.available,
                        "url": result.url,
                        "stock_label": result.stock_label,
                    })
                    print(f"R$ {result.price:,.2f}")
                else:
                    print("sem resultado")
            
            prices.sort(key=lambda p: p["price"])
            results[display_name] = {
                "search_term": search_term,
                "timestamp": datetime.now().isoformat(),
                "count": len(prices),
                "prices": prices,
            }
            print(f"  TOTAL: {len(prices)} precos")
        
        await browser.close()
    
    return results


def save_json(data: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"precos_ram_{ts}.json"
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[JSON] Salvo: {filepath}")
    return filepath


def save_sqlite_inserts(data: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"inserts_ram_{ts}.sql"
    filepath = OUTPUT_DIR / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("-- Sincronizacao de precos locais para VM\n")
        f.write(f"-- Gerado em: {datetime.now().isoformat()}\n\n")
        f.write("PRAGMA journal_mode = WAL;\n\n")
        
        for display_name, info in data.items():
            if "error" in info:
                f.write(f"-- SKIP {display_name}: {info['error']}\n")
                continue
            for p in info.get("prices", []):
                url = p.get("url") or ""
                stock = p.get("stock_label") or ""
                search_term = info.get("search_term", display_name)
                payload = json.dumps({"url": url, "stock_label": stock, "search_term": search_term})
                f.write(
                    f"INSERT INTO price_history "
                    f"(store_id, product_name, price, available, scraped_at, data) "
                    f"VALUES ("
                    f"'{p['store']}', "
                    f"'{display_name}', "
                    f"{p['price']}, "
                    f"{1 if p.get('available') else 0}, "
                    f"datetime('now'), "
                    f"'{payload}'"
                    f");\n"
                )
            f.write("\n")
    
    print(f"[SQL] Salvo: {filepath}")
    return filepath


def print_summary(data: dict):
    print("\n" + "="*60)
    print("RESUMO DA COLETA")
    print("="*60)
    total = 0
    for name, info in data.items():
        if "error" in info:
            print(f"[ERRO] {name}: {info['error']}")
        else:
            n = info["count"]
            total += n
            print(f"[OK] {name}: {n} precos")
            for p in info["prices"][:2]:
                print(f"   - {p['store']}: R$ {p['price']:,.2f}")
    print(f"\nTotal de precos coletados: {total}")


async def main():
    parser = argparse.ArgumentParser(description="Scraper local de precos de RAM")
    parser.add_argument("--upload", action="store_true", help="Sobe os arquivos pro servidor via SCP")
    parser.add_argument("--vm", default="ubuntu@137.131.159.91", help="Endereco SSH da VM")
    parser.add_argument("--key", default=None, help="Caminho da chave SSH")
    args = parser.parse_args()
    
    print("="*60)
    print("PrecoBot - Scraper LOCAL (IP residencial)")
    print("="*60)
    print(f"Inicio: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Produtos: {len(PRODUCTS)}")
    print(f"Lojas: KaBuM, Pichau, Amazon")
    
    data = await collect_all()
    
    json_path = save_json(data)
    sql_path = save_sqlite_inserts(data)
    print_summary(data)
    
    if args.upload:
        cmd = ["scp"]
        if args.key:
            cmd += ["-i", args.key]
        cmd += [str(json_path), str(sql_path), f"{args.vm}:/home/ubuntu/precosbot/local_exports/"]
        print(f"\n[UPLOAD] Enviando para {args.vm}...")
        ret = subprocess.run(cmd)
        if ret.returncode != 0:
            print(f"[UPLOAD] Falhou (exit {ret.returncode})")
        else:
            print("[UPLOAD] Completo!")
    
    print(f"\nFim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
