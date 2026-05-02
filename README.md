# PreçoBot — Brazilian Hardware Price Toolkit

Agentic scraping toolkit for Brazilian e-commerce stores: KaBuM!, Pichau, Terabyte Shop, Mercado Livre, Amazon BR.

Designed to be consumed by [hermes-agent](https://github.com/NousResearch/hermes-agent) via the subprocess CLI bridge (`agent_api.py`). No Discord bot, no fixed scheduler — all orchestration is done by the AI agent.

---

## Stores

| Store | Scraper | Notes |
|-------|---------|-------|
| KaBuM! | Playwright | `article.productCard` |
| Pichau | Playwright | React/MUI — waits for `networkidle` |
| Terabyte Shop | Playwright | `div.pbox` |
| Mercado Livre | Playwright + cookies | OCI IP blocked at CDN — needs `ml_cookies.json` |
| Amazon BR | Playwright | Anti-bot: random delay + CAPTCHA detection |

---

## Python API

```python
from toolkit import scrape, scrape_and_store, get_latest, get_history, best_deal, compare, get_analysis

# Live scrape (30-120s)
results = await scrape_and_store("RTX 4060 Ti")

# Cached prices
records = await get_latest("RTX 4060 Ti")

# Best deal from cache
deal = await best_deal("RTX 4060 Ti")

# Price trend analysis
analysis = await get_analysis("RTX 4060 Ti", days=30)
```

---

## CLI (agent_api.py)

```bash
python agent_api.py check "RTX 4060 Ti"
python agent_api.py latest "RTX 4060 Ti"
python agent_api.py history "RTX 4060 Ti" 7
python agent_api.py analysis "RTX 4060 Ti" 30
python agent_api.py best-deal "RTX 4060 Ti"
python agent_api.py compare "RTX 4060" | "RTX 4070"
python agent_api.py list-tracked
python agent_api.py db-stats
```

All commands output JSON. Exit 1 with `{"success": false, "error": "..."}` on failure.

---

## Project Structure

```
toolkit.py              # Main async API
agent_api.py            # CLI bridge for hermes-agent
config.py               # Store config (URL templates, display names, colors)
core/
  product_manager.py    # Name normalization, URL generation
  executor.py           # Playwright execution engine (shared browser, sequential)
db/
  database.py           # SQLite init, WAL config, get_db context manager
  repositories/
    price_repo.py       # Price history CRUD
    alert_repo.py       # User alert CRUD
    tracking_repo.py    # Tracked products CRUD
scrapers/
  base.py               # BaseScraper, ScrapeResult
  kabum.py / pichau.py / terabyte.py / amazon.py / mercadolivre.py
utils/
  formatters.py         # format_price_brl, format_store_name
tests/
  test_all.py           # Quick validation
  test_repositories.py  # DB layer (in-memory SQLite)
  test_executor.py      # Executor (mocked Playwright)
  test_embeds.py        # Toolkit function tests
  test_integration.py   # Data flow tests
  test_product_manager.py
```

---

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
python tests/test_all.py     # Verify imports
python agent_api.py db-stats # Verify DB
```

---

## hermes-agent Integration

hermes calls `agent_api.py` as a subprocess through `precosbot.py` in the hermes tools directory.
The hermes gateway runs as `hermes.service` on the OCI VM and connects to Discord.

See `AGENTS.md` for full OCI deployment details.

---

## Database

SQLite at `precobot.db`. WAL mode. Tables:

- `price_history` — one row per scrape per store per product
- `user_alerts` — price alert targets per Discord user
- `tracked_products` — products under active monitoring
- `scheduler_locks` — concurrency guards (legacy, unused by toolkit)

---

## Adding a Store

1. Create `scrapers/novaloja.py` — subclass `BaseScraper`, implement `async scrape() -> ScrapeResult`
2. Add to `config.py`: `STORE_URL_TEMPLATES`, `STORE_DISPLAY_NAMES`, `STORE_COLORS`
3. Register in `scrapers/__init__.py` under `BROWSER_SCRAPERS` or `HTTP_SCRAPERS`

---

## Dependencies

| Package | Use |
|---------|-----|
| `playwright` | Headless browser scraping |
| `aiosqlite` | Async SQLite |
| `httpx` | HTTP requests |
| `python-dotenv` | `.env` loading |
| `pytest` / `pytest-asyncio` | Tests |

---

MIT License
