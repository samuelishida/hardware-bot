#!/usr/bin/env python3
"""
agent_api.py — CLI bridge for hermes-agent integration.

Called as a subprocess by the hermes precosbot tool.

Commands:
  check <product>                Live scrape + store to DB (30-120s)
  latest <product>               Latest cached prices from DB
  history <product> [days]       Price history from DB (default 7 days)
  analysis <product> [days]      Per-store min/max/avg stats (default 30 days)
  best-deal <product>            Cheapest available cached price
  compare <product1> | <p2> ...  Compare latest prices for multiple products
  scrape-and-store <product>     Live scrape + persist (same as check, alias)
  list-tracked                   List all active tracked products
  db-stats                       Database statistics
"""

from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _err(msg: str) -> None:
    print(json.dumps({"success": False, "error": msg}))
    sys.exit(1)


async def cmd_check(product: str) -> None:
    from toolkit import scrape_and_store
    from config import STORE_DISPLAY_NAMES

    results = await scrape_and_store(product)

    print(json.dumps({
        "success": True,
        "product": product,
        "results": [
            {
                "store_id": r.store_id,
                "store_name": STORE_DISPLAY_NAMES.get(r.store_id, r.store_id),
                "price": r.price,
                "available": r.available,
                "stock_label": r.stock_label,
                "url": r.url,
            }
            for r in results
        ],
    }))


async def cmd_latest(product: str) -> None:
    from toolkit import get_latest
    from config import STORE_DISPLAY_NAMES

    records = await get_latest(product)
    print(json.dumps({
        "success": True,
        "product": product,
        "results": [
            {
                "store_id": r.store_id,
                "store_name": STORE_DISPLAY_NAMES.get(r.store_id, r.store_id),
                "price": r.price,
                "available": r.available,
                "stock_label": r.stock_label,
                "url": r.url,
                "scraped_at": r.scraped_at,
            }
            for r in records
        ],
    }))


async def cmd_history(product: str, days: int) -> None:
    from toolkit import get_history
    from config import STORE_DISPLAY_NAMES

    records = await get_history(product, days=days)
    print(json.dumps({
        "success": True,
        "product": product,
        "days": days,
        "records": [
            {
                "store_id": r.store_id,
                "store_name": STORE_DISPLAY_NAMES.get(r.store_id, r.store_id),
                "price": r.price,
                "available": r.available,
                "scraped_at": r.scraped_at,
                "url": r.url,
            }
            for r in records
        ],
    }))


async def cmd_analysis(product: str, days: int) -> None:
    from toolkit import get_analysis
    from config import STORE_DISPLAY_NAMES

    data = await get_analysis(product, days=days)
    # Annotate store names in per_store dict
    per_store_named = {
        STORE_DISPLAY_NAMES.get(sid, sid): stats
        for sid, stats in data["per_store"].items()
    }
    data["per_store"] = per_store_named
    if data["overall_min"]:
        sid = data["overall_min"]["store_id"]
        data["overall_min"]["store_name"] = STORE_DISPLAY_NAMES.get(sid, sid)
    print(json.dumps({"success": True, **data}))


async def cmd_best_deal(product: str) -> None:
    from toolkit import best_deal
    from config import STORE_DISPLAY_NAMES

    record = await best_deal(product)
    if record is None:
        print(json.dumps({"success": True, "product": product, "result": None}))
        return
    print(json.dumps({
        "success": True,
        "product": product,
        "result": {
            "store_id": record.store_id,
            "store_name": STORE_DISPLAY_NAMES.get(record.store_id, record.store_id),
            "price": record.price,
            "available": record.available,
            "stock_label": record.stock_label,
            "url": record.url,
            "scraped_at": record.scraped_at,
        },
    }))


async def cmd_compare(products: list[str]) -> None:
    from toolkit import compare
    from config import STORE_DISPLAY_NAMES

    data = await compare(products)
    output = {}
    for product, records in data.items():
        output[product] = [
            {
                "store_id": r.store_id,
                "store_name": STORE_DISPLAY_NAMES.get(r.store_id, r.store_id),
                "price": r.price,
                "available": r.available,
                "scraped_at": r.scraped_at,
            }
            for r in records
        ]
    print(json.dumps({"success": True, "comparison": output}))


async def cmd_list_tracked() -> None:
    from db.repositories import get_all_tracked_products

    products = await get_all_tracked_products()
    print(json.dumps({"success": True, "tracked": products}))


async def cmd_db_stats() -> None:
    from db.database import get_db_stats

    stats = await get_db_stats()
    print(json.dumps({"success": True, "stats": stats}))


async def main() -> None:
    if len(sys.argv) < 2:
        _err(
            "Usage: agent_api.py <check|latest|history|analysis|best-deal"
            "|compare|scrape-and-store|list-tracked|db-stats> [args...]"
        )

    from db.database import init_db
    await init_db()

    cmd = sys.argv[1]

    if cmd in ("check", "scrape-and-store"):
        if len(sys.argv) < 3:
            _err(f"{cmd} requires <product>")
        await cmd_check(" ".join(sys.argv[2:]))

    elif cmd == "latest":
        if len(sys.argv) < 3:
            _err("latest requires <product>")
        await cmd_latest(" ".join(sys.argv[2:]))

    elif cmd == "history":
        if len(sys.argv) < 3:
            _err("history requires <product> [days]")
        parts = sys.argv[2:]
        days = 7
        if parts and parts[-1].isdigit():
            days = int(parts[-1])
            parts = parts[:-1]
        await cmd_history(" ".join(parts), days)

    elif cmd == "analysis":
        if len(sys.argv) < 3:
            _err("analysis requires <product> [days]")
        parts = sys.argv[2:]
        days = 30
        if parts and parts[-1].isdigit():
            days = int(parts[-1])
            parts = parts[:-1]
        await cmd_analysis(" ".join(parts), days)

    elif cmd == "best-deal":
        if len(sys.argv) < 3:
            _err("best-deal requires <product>")
        await cmd_best_deal(" ".join(sys.argv[2:]))

    elif cmd == "compare":
        # Products separated by | in argv or as multiple args split by literal |
        raw = " ".join(sys.argv[2:])
        products = [p.strip() for p in raw.split("|") if p.strip()]
        if not products:
            _err("compare requires <product1> | <product2> ...")
        await cmd_compare(products)

    elif cmd == "list-tracked":
        await cmd_list_tracked()

    elif cmd == "db-stats":
        await cmd_db_stats()

    else:
        _err(f"Unknown command: {cmd}")


if __name__ == "__main__":
    asyncio.run(main())
