---
name: precosbot
description: "Check and track product prices across Brazilian e-commerce stores."
version: 1.0.0
metadata:
  hermes:
    tags: [prices, shopping, brazil, e-commerce]
    category: shopping
    config:
      - key: precosbot.path
        description: Path to the precosbot repository
        default: "/home/ubuntu/precosbot"
        prompt: "PrecoBot repository path"
---

# PrecoBot - Brazilian Price Tracker

You have tools to check prices across Brazilian e-commerce stores.

## Tools

| Tool | Speed | Use When |
|------|-------|----------|
| `precosbot_check` | 30-120s | User wants live current prices (raw scrape) |
| `precosbot_agent` | up to ~180s | User wants a *confident* answer: validated prices + deal verdict |
| `precosbot_latest` | instant | User wants last cached scan |
| `precosbot_history` | instant | User asks about price trends |
| `precosbot_list_tracked` | instant | User asks what is being monitored |
| `precosbot_db_stats` | instant | User asks about data coverage |

## `precosbot_check` vs `precosbot_agent`

- **`precosbot_check`** — raw live scrape. Fast-ish, returns whatever the scrapers
  found. No validation: a glitched price (e.g. "R$ 0,99" typo) is returned as-is.
- **`precosbot_agent`** — full multi-agent pipeline. Scrapes, then an analyst agent
  cross-checks each price against 30-day history (flags suspicious outliers), and a
  deal agent decides whether the best price beats an optional `target_price`.
  Returns `results` (validated), `deal` (verdict + savings), `summary` (human text),
  and `trace` (which agents ran). Use it when the user wants a recommendation, not
  just numbers — or when a `precosbot_check` result looks off and you want a second
  opinion.

## Workflow

1. For "price of X?" - call `precosbot_latest` first (instant).
   If stale/missing, warn user scraping takes 30-120s, then call `precosbot_check`.
2. For "is X a good deal / should I buy X at R$Y?" - call `precosbot_agent` with
   `target_price=Y`. Read `summary` and relay it; cite `deal.savings_pct` if present.
3. Sort results cheapest first. Flag unavailable stores.
4. Format prices in BRL: R$ 1.299,00

## MCP server (optional)

`python -m agents.mcp_server` exposes the same pipeline as an MCP server (stdio)
with tools `run_agent`, `get_latest`, `get_history`, `self_healing_status`. It is a
thin facade over the same code — no extra logic.

> **VM warning (1 GB RAM):** `run_agent` via MCP runs the *same* Lightpanda
> pipeline as `precosbot_agent`. Do **not** run `agent` (hermes) and the MCP
> server in parallel for the same product — SQLite writes are serialized and safe,
> but two concurrent browsers will exhaust RAM. Run one at a time.

## Stores

Amazon BR, KaBuM!, Pichau, Terabyte Shop

## Hardware / PC Component Search Pitfalls

When searching for CPUs, GPUs, motherboards, and other PC hardware, store scrapers are finicky:

1. **Use the full canonical product name** — "processador amd ryzen 7 5700x3d" yields better matches than "ryzen 5700x3d".
   - KaBuM! / Pichau search often returns "Não encontrado" for abbreviated names.
   - Terabyte may return the product page but mark it **Esgotado** rather than a price.
2. **A live scrape with no price does NOT mean unavailable everywhere.**
   - KaBuM! / Pichau / Terabyte may have the product page but no stock.

## References

- `references/kabum-nextjs-json-source.md` — How to extract structured product data from KaBuM!'s embedded `__NEXT_DATA__` JSON when the Lightpanda scraper fails.
