"""
utils/history_logger.py — Lightweight append-only markdown log for every scrape.

Since there's no git repository, HISTORY.md is the durable journal.
Format: one entry per line as machine-parseable markdown table rows.
"""

from __future__ import annotations
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

HISTORY_PATH: Path = Path(__file__).parent.parent / "HISTORY.md"


def _ensure_file() -> None:
    if not HISTORY_PATH.exists():
        HISTORY_PATH.write_text(
            "# PreçoBot Scrape History\n\n"
            "| timestamp | store | product | price | available | url |\n"
            "|-----------|-------|---------|-------|-----------|-----|\n"
            "\n"
        )


def log_scrape(
    store_id: str,
    product: str,
    price: Optional[float],
    available: bool,
    url: Optional[str],
) -> None:
    """Append one scrape result to HISTORY.md."""
    _ensure_file()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    p_str = f"R$ {price:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if price is not None else "—"
    a_str = "✅" if available else "❌"
    u_str = url or ""
    line = f"| {ts} | {store_id} | {product} | {p_str} | {a_str} | {u_str} |\n"
    with HISTORY_PATH.open("a") as f:
        f.write(line)
