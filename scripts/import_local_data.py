#!/usr/bin/env python3
"""
import_local_data.py - Importa dados JSON coletados localmente para o SQLite da VM.

Uso:
    python scripts/import_local_data.py local_exports/precos_ram_20260502_1633.json
"""
from __future__ import annotations
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import get_db
from db.repositories.price_repo import insert_price


async def import_json(filepath: str):
    path = Path(filepath)
    if not path.exists():
        print(f"Arquivo nao encontrado: {filepath}")
        sys.exit(1)
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    total = 0
    for display_name, info in data.items():
        if "error" in info:
            print(f"[SKIP] {display_name}: {info['error']}")
            continue
        
        for p in info.get("prices", []):
            await insert_price(
                store_id=p["store"],
                price=p["price"],
                available=p.get("available", False),
                stock_label=p.get("stock_label", ""),
                url=p.get("url", ""),
                product_name=display_name,
                search_term=info.get("search_term", display_name),
            )
            total += 1
        print(f"[OK] {display_name}: {len(info.get('prices', []))} precos importados")
    
    print(f"\nTotal de precos importados: {total}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/import_local_data.py <arquivo.json>")
        sys.exit(1)
    
    asyncio.run(import_json(sys.argv[1]))
