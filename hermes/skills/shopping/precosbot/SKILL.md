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
| `precosbot_check` | 30-120s | User wants live current prices |
| `precosbot_latest` | instant | User wants last cached scan |
| `precosbot_history` | instant | User asks about price trends |
| `precosbot_list_tracked` | instant | User asks what is being monitored |
| `precosbot_db_stats` | instant | User asks about data coverage |

## Workflow

1. For "price of X?" - call `precosbot_latest` first (instant).
   If stale/missing, warn user scraping takes 30-120s, then call `precosbot_check`.
2. Sort results cheapest first. Flag unavailable stores.
3. Format prices in BRL: R$ 1.299,00

## Stores

Amazon BR, KaBuM!, Pichau, Terabyte Shop, Mercado Livre (new + used)

Note: Mercado Livre may be blocked from OCI IPs. Other stores are reliable.

## Hardware / PC Component Search Pitfalls

When searching for CPUs, GPUs, motherboards, and other PC hardware, store scrapers are finicky:

1. **Use the full canonical product name** — "processador amd ryzen 7 5700x3d" yields better matches than "ryzen 5700x3d".
   - KaBuM! / Pichau search often returns "Não encontrado" for abbreviated names.
   - Terabyte may return the product page but mark it **Esgotado** rather than a price.
2. **A live scrape with no price does NOT mean unavailable everywhere.**
   - KaBuM! / Pichau / Terabyte may have the product page but no stock.
   - Mercado Livre often has the only live listing for niche or high-demand PC parts.
3. **Mercado Livre used filter is unreliable** — the `_Condicao_2230581` suffix is sometimes stripped by ML redirects, causing the "usado" scraper to fall back to new listings.

## References

- `references/kabum-nextjs-json-source.md` — How to extract structured product data from KaBuM!'s embedded `__NEXT_DATA__` JSON when the Playwright scraper fails.
