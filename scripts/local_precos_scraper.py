#!/usr/bin/env python3
"""
local_precos_scraper.py — Script para rodar LOCAL (IP residencial brasileiro).

LEGADO (Inc 4 Lightpanda): este script usa Playwright diretamente e roda apenas
em dev local (Windows/Linux/Mac com IP residencial). NÃO está no caminho de runtime
do precosbot (executor + scrapers usam a facade Lightpanda). Para dev local com
Lightpanda, use WSL2 (sem binário Windows). Fora de escopo da migração.

Roda em qualquer PC Windows/Linux/Mac com IP de casa para evitar cloud block.
Coleta preços de RAM DDR4/DDR5 via Playwright + PreçoBot.
Exporta os dados em JSON para sincronizar com a VM na OCI depois.

Instalação:
    git clone <url-do-repo> precosbot
    cd precosbot
    python -m venv venv
    venv\Scripts\pip install -r requirements.txt    # Windows
    venv/bin/pip install -r requirements.txt       # Linux/Mac
    playwright install chromium

Uso:
    python local_precos_scraper.py              # Coleta tudo
    python local_precos_scraper.py --upload     # Coleta + sobe JSON pro servidor
"""
from __future__ import annotations
import asyncio
import argparse
import json
import os
import sys
import io
from datetime import datetime
from pathlib import Path

# Force UTF-8 on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Adiciona o diretório do repo ao path se rodar fora dele
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from playwright.async_api import async_playwright
    from toolkit import scrape_and_store
except ImportError as e:
    print(f"Erro de importação: {e}")
    print("Verifique se está no diretório do precosbot e se o venv está ativado.")
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


async def collect_all():
    """Coleta preços de todos os produtos."""
    results = {}
    
    for search_term, display_name in PRODUCTS:
        print(f"\n🔍 Coletando: {display_name}")
        try:
            items = await asyncio.wait_for(scrape_and_store(search_term), timeout=120)
            priced = [r for r in items if r.price is not None]
            priced.sort(key=lambda r: r.price)
            
            results[display_name] = {
                "search_term": search_term,
                "timestamp": datetime.now().isoformat(),
                "count": len(priced),
                "prices": [
                    {
                        "store": r.store_id,
                        "price": r.price,
                        "available": r.available,
                        "url": r.url,
                        "stock_label": r.stock_label,
                    }
                    for r in priced
                ]
            }
            print(f"  ✅ {len(priced)} preços encontrados")
            for r in priced[:3]:
                print(f"     {r.store_id}: R$ {r.price:,.2f}")
        except asyncio.TimeoutError:
            print(f"  ⏱️ TIMEOUT — pulando")
            results[display_name] = {"search_term": search_term, "error": "timeout"}
        except Exception as e:
            print(f"  ❌ ERRO: {e}")
            results[display_name] = {"search_term": search_term, "error": str(e)}
    
    return results


def save_json(data: dict):
    """Salva resultado em JSON datado."""
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"precos_ram_{ts}.json"
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n💾 JSON salvo: {filepath}")
    return filepath


def save_sqlite_inserts(data: dict) -> str:
    """Gera SQL INSERT para sincronizar com o SQLite da VM."""
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"inserts_ram_{ts}.sql"
    filepath = OUTPUT_DIR / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("-- Sincronização de preços locais para VM\n")
        f.write(f"-- Gerado em: {datetime.now().isoformat()}\n\n")
        f.write("PRAGMA journal_mode = WAL;\n\n")
        
        for display_name, info in data.items():
            if "error" in info:
                f.write(f"-- SKIP {display_name}: {info['error']}\n")
                continue
            for p in info.get("prices", []):
                url = p["url"] or ""
                stock = p["stock_label"] or ""
                f.write(
                    f"INSERT INTO price_history "
                    f"(store_id, product_name, price, available, scraped_at, data) "
                    f"VALUES ("
                    f"'{p['store']}', "
                    f"'{display_name}', "
                    f"{p['price']}, "
                    f"{1 if p['available'] else 0}, "
                    f"datetime('now'), "
                    f"'{json.dumps({'url': url, 'stock_label': stock})}'"
                    f");\n"
                )
            f.write("\n")
    
    print(f"💾 SQL salvo: {filepath}")
    return filepath


def print_summary(data: dict):
    """Exibe resumo no terminal."""
    print("\n" + "="*60)
    print("RESUMO DA COLETA")
    print("="*60)
    total = 0
    for name, info in data.items():
        if "error" in info:
            print(f"❌ {name}: {info['error']}")
        else:
            n = info["count"]
            total += n
            print(f"✅ {name}: {n} preços")
            for p in info["prices"][:2]:
                print(f"   └─ {p['store']}: R$ {p['price']:,.2f}")
    print(f"\n📊 Total de preços coletados: {total}")


async def main():
    parser = argparse.ArgumentParser(description="Scraper local de preços de RAM")
    parser.add_argument("--upload", action="store_true", help="Sobe o JSON pro servidor via SCP após coleta")
    parser.add_argument("--vm", default="ubuntu@137.131.159.91", help="Endereço SSH da VM")
    parser.add_argument("--key", default=None, help="Caminho da chave SSH")
    args = parser.parse_args()
    
    print("="*60)
    print("PreçoBot — Scraper LOCAL (IP residencial)")
    print("="*60)
    print(f"Início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Produtos: {len(PRODUCTS)}")
    
    # COLETA
    data = await collect_all()
    
    # SALVA
    json_path = save_json(data)
    sql_path = save_sqlite_inserts(data)
    print_summary(data)
    
    # UPLOAD (opcional)
    if args.upload:
        key_flag = f"-i {args.key}" if args.key else ""
        remote_path = f"{args.vm}:/home/ubuntu/precosbot/local_exports/"
        print(f"\n☁️  Enviando para {remote_path}...")
        os.system(f"scp {key_flag} {json_path} {sql_path} {remote_path}")
        print("✅ Upload completo!")
    
    print(f"\nFim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
