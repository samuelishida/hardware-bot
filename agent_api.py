#!/usr/bin/env python3
"""
agent_api.py — CLI bridge for hermes-agent integration.

Called as a subprocess by the hermes precosbot tool.

Commands:
  check <product>                Live scrape + store to DB (30-120s)
  latest <product>               Latest cached prices from DB
  history <product> [--days N]   Price history from DB (default 7 days)
  analysis <product> [--days N]  Per-store min/max/avg stats (default 30 days)
  best-deal <product>            Cheapest available cached price
  compare <product1> | <p2> ...  Compare latest prices for multiple products
  scrape-and-store <product>     Live scrape + persist (same as check, alias)
  list-tracked                   List all active tracked products
  db-stats                       Database statistics
  agent <product> [-- <target_price>] Full MAS pipeline (scrape → validate → deal)
  agent-traces [limit]           List recent MAS pipeline runs (default 10)
"""

from __future__ import annotations
import asyncio
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _err(msg: str) -> None:
    print(json.dumps({"success": False, "error": msg}))
    sys.exit(1)


def _store_dict(r, *, with_scraped_at: bool = False) -> dict:
    """Serializa um record (ScrapeResult/PriceRecord) para o JSON de saída."""
    from config import STORE_DISPLAY_NAMES

    d = {
        "store_id": r.store_id,
        "store_name": STORE_DISPLAY_NAMES.get(r.store_id, r.store_id),
        "price": r.price,
        "available": r.available,
        "stock_label": r.stock_label,
        "url": r.url,
    }
    if with_scraped_at:
        d["scraped_at"] = r.scraped_at
    return d


async def cmd_check(product: str) -> None:
    from toolkit import scrape_and_store

    results = await scrape_and_store(product)

    print(json.dumps({
        "success": True,
        "product": product,
        "results": [_store_dict(r) for r in results],
    }))


async def cmd_latest(product: str) -> None:
    from toolkit import get_latest

    records = await get_latest(product)
    print(json.dumps({
        "success": True,
        "product": product,
        "results": [_store_dict(r, with_scraped_at=True) for r in records],
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

    record = await best_deal(product)
    if record is None:
        print(json.dumps({"success": True, "product": product, "result": None}))
        return
    print(json.dumps({
        "success": True,
        "product": product,
        "result": _store_dict(record, with_scraped_at=True),
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


async def cmd_agent(product: str, target_price: float | None = None) -> None:
    """Run the full MAS pipeline (scrape → validate → deal analysis).

    ``AgentResult.status="error"`` → ainda ``success: true`` com ``status``
    (o pipeline rodou; o resultado é negativo). Exceção não tratada → ``_err``.
    """
    from agents.orchestrator import run_agent_pipeline  # lazy: patchável em testes

    try:
        result = await run_agent_pipeline(product, target_price=target_price)
    except Exception as e:
        _err(f"agent pipeline falhou: {e}")
    print(json.dumps(result.to_dict()))


def _parse_agent_args(argv: list[str]) -> tuple[str, float | None]:
    """Parse ``agent <product> [-- <target_price>]``.

    ``target_price`` é opcional e exige o separador ``--`` para não colidir com
    nomes de produto que terminam em dígitos (ex.: ``RTX 4060``). Sem ``--``,
    todo o argv é o produto.
    Raises ``ValueError`` se não houver produto ou se o target for inválido.
    """
    parts = list(argv)
    target_price: float | None = None
    if "--" in parts:
        idx = parts.index("--")
        product_tokens = parts[:idx]
        target_tokens = parts[idx + 1:]
        if len(target_tokens) == 1:
            try:
                target_price = float(target_tokens[0])
            except ValueError:
                raise ValueError("agent: target_price inválido")
            if not math.isfinite(target_price) or target_price < 0:
                raise ValueError("agent: target_price inválido")
        elif target_tokens:
            raise ValueError("agent: target_price inválido após '--'")
    else:
        product_tokens = parts
    if not product_tokens:
        raise ValueError("agent requires <product> [-- <target_price>]")
    return " ".join(product_tokens), target_price


async def cmd_agent_traces(limit: int = 10) -> None:
    """List the most recent MAS pipeline runs (``agent_runs`` table).

    Runs abortados (``finished_at`` nulo) aparecem com ``status="incomplete"``.
    """
    from db.repositories.run_repo import get_recent_runs

    runs = await get_recent_runs(limit)
    print(json.dumps({"success": True, "runs": runs}))


def _split_days(argv: list[str], default: int) -> tuple[str, int]:
    """Separa ``<product> [--days N]`` de forma inequívoca.

    Usa o flag explícito ``--days`` (em vez de tratar o último token como dias)
    para não corromper nomes de produto que terminam em dígitos (ex.: ``RTX 4060``).
    """
    parts = list(argv)
    days = default
    if "--days" in parts:
        idx = parts.index("--days")
        if idx + 1 < len(parts) and parts[idx + 1].isdigit():
            days = int(parts[idx + 1])
            del parts[idx : idx + 2]
        else:
            raise ValueError("--days requer um valor inteiro")
    days = min(max(1, days), 3650)
    return " ".join(parts), days


async def main() -> None:
    if len(sys.argv) < 2:
        _err(
            "Usage: agent_api.py <check|latest|history|analysis|best-deal"
            "|compare|scrape-and-store|list-tracked|db-stats|agent|agent-traces> [args...]"
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
            _err("history requires <product> [--days N]")
        try:
            product, days = _split_days(sys.argv[2:], 7)
        except ValueError as e:
            _err(str(e))
        await cmd_history(product, days)

    elif cmd == "analysis":
        if len(sys.argv) < 3:
            _err("analysis requires <product> [--days N]")
        try:
            product, days = _split_days(sys.argv[2:], 30)
        except ValueError as e:
            _err(str(e))
        await cmd_analysis(product, days)

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

    elif cmd == "agent":
        try:
            product, target_price = _parse_agent_args(sys.argv[2:])
        except ValueError as e:
            _err(str(e))
        await cmd_agent(product, target_price)

    elif cmd == "agent-traces":
        limit = 10
        if len(sys.argv) >= 3 and sys.argv[2].isdigit():
            limit = min(max(1, int(sys.argv[2])), 100)
        await cmd_agent_traces(limit)

    else:
        _err(f"Unknown command: {cmd}")


if __name__ == "__main__":
    asyncio.run(main())
