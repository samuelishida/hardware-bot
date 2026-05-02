# AGENTS.md — PreçoBot

Agentic scraping toolkit for Brazilian hardware stores (KaBuM, Pichau, Terabyte, Mercado Livre, Amazon BR).
Consumed by hermes-agent via subprocess bridge (`agent_api.py`). No Discord bot, no scheduler.

## Architecture

```
toolkit.py                  # Main async Python API (scrape, get_latest, get_history, ...)
agent_api.py                # CLI subprocess bridge for hermes-agent
config.py                   # Store config (URL templates, display names, colors)
.env                        # Optional env vars (PRICE_DROP_THRESHOLD_PCT)
core/
  product_manager.py        # Product name normalization, search URL generation
  executor.py               # Playwright scraper execution engine (1-browser shared session)
db/
  database.py               # SQLite setup (aiosqlite), init_db, get_db context manager
  repositories/
    price_repo.py           # Price history CRUD
    alert_repo.py           # User price alert CRUD
    tracking_repo.py        # Tracked products CRUD
scrapers/
  base.py                   # BaseScraper, ScrapeResult dataclass
  kabum.py                  # KaBuM! (Playwright)
  pichau.py                 # Pichau (Playwright)
  terabyte.py               # Terabyte Shop (Playwright)
  amazon.py                 # Amazon BR (Playwright)
  mercadolivre.py           # Mercado Livre (Playwright, cookie-based)
utils/
  formatters.py             # format_price_brl, format_store_name, normalize_search_term
tests/
  test_all.py               # Quick validation runner
  test_product_manager.py   # ProductManager unit tests
  test_repositories.py      # Repository unit tests (in-memory SQLite)
  test_executor.py          # Executor unit tests (mocked Playwright)
  test_embeds.py            # Toolkit unit tests
  test_integration.py       # Integration tests (data flow)
```

## Toolkit API (toolkit.py)

```python
await scrape(product)                    # Live scrape, returns list[ScrapeResult]
await scrape_and_store(product)          # Live scrape + persist to DB
await get_latest(product)               # Latest cached prices from DB
await get_history(product, days=7)      # Price history, all stores, sorted by time
await best_deal(product, live=False)    # Cheapest available PriceRecord (live=True re-scrapes)
await compare(["RTX 4060", "RTX 4070"]) # dict[product, list[PriceRecord]]
await get_analysis(product, days=30)    # {per_store: {min/max/avg/n}, overall_min}
```

## agent_api.py commands

```
python agent_api.py check <product>                Live scrape + store (30-120s)
python agent_api.py latest <product>               Latest cached prices
python agent_api.py history <product> [days]       Price history (default 7 days)
python agent_api.py analysis <product> [days]      Per-store stats (default 30 days)
python agent_api.py best-deal <product>            Cheapest cached price
python agent_api.py compare <p1> | <p2> | ...     Multi-product comparison
python agent_api.py scrape-and-store <product>     Alias for check
python agent_api.py list-tracked                   List tracked products in DB
python agent_api.py db-stats                       DB row counts and size
```

All commands output JSON to stdout. Exit 1 with `{"success": false, "error": "..."}` on error.

## Key Patterns

- **Scrapers**: Subclass `BaseScraper`, implement `async scrape() -> ScrapeResult`. Always instantiate with kwargs: `cls(browser=b, search_term=term)`.
- **Executor**: `scrape_product(BROWSER_SCRAPERS, HTTP_SCRAPERS, search_term)` — runs all scrapers sequentially sharing one Playwright browser. Per-scraper timeout: 90s.
- **Python 3.12**: OCI VM runs Ubuntu 24.04 + Python 3.12. Use `from __future__ import annotations` for `X | Y` unions.
- **SQLite**: `precobot.db` at project root. WAL mode. Tables: `price_history`, `user_alerts`, `tracked_products`, `scheduler_locks`.
- **Mercado Livre (VM)**: OCI datacenter IP is CDN-blocked. ML scraper uses cookie persistence (`ml_cookies.json`). May still fail on first run if cookies are absent.

## OCI Deployment

```bash
SSH_KEY=~/.ssh/oci_yvy
VM=ubuntu@137.131.159.91
REMOTE=/home/ubuntu/precosbot

# Deploy full toolkit
ssh -i $SSH_KEY $VM "cd $REMOTE && git pull && pip install -r requirements.txt"

# Or deploy single file
scp -i $SSH_KEY toolkit.py $VM:$REMOTE/toolkit.py
scp -i $SSH_KEY agent_api.py $VM:$REMOTE/agent_api.py

# Restart hermes (the service that calls precosbot)
ssh -i $SSH_KEY $VM "sudo systemctl restart hermes"

# Logs
ssh -i $SSH_KEY $VM "journalctl -u hermes -f"
ssh -i $SSH_KEY $VM "journalctl -u hermes -n 100 --no-pager"
```

### Services on VM

| Service | File | Role |
|---------|------|------|
| `hermes.service` | `/etc/systemd/system/hermes.service` | hermes-agent Discord gateway |
| ~~`precosbot.service`~~ | deleted | replaced by hermes |

hermes.service:
```ini
[Unit]
Description=Hermes Agent Gateway
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu
EnvironmentFile=/home/ubuntu/.hermes/.env
ExecStart=/home/ubuntu/.hermes/hermes-agent/venv/bin/hermes gateway run --accept-hooks
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### hermes config (`~/.hermes/config.yaml`)

```yaml
model:
  base_url: http://localhost:11434/v1
  default: kimi-k2.6:cloud
  provider: auto
skills:
  config:
    precosbot:
      path: /home/ubuntu/precosbot
```

### hermes env (`~/.hermes/.env`)

```
OPENAI_API_KEY=ollama
DISCORD_BOT_TOKEN=<token>
DISCORD_HOME_CHANNEL=<channel_id>
GATEWAY_ALLOW_ALL_USERS=true
```

## hermes Tool Registration

Tool: `~/.hermes/hermes-agent/tools/precosbot.py` (or `E:\Code\hermes-agent\tools\precosbot.py`)
Skill: `~/.hermes/skills/shopping/precosbot/SKILL.md`
Core tools: `precosbot_check`, `precosbot_latest`, `precosbot_history`, `precosbot_list_tracked`, `precosbot_db_stats`

## Adding a New Store

1. Create `scrapers/novaloja.py` inheriting `BaseScraper`
2. Add to `config.py`: `STORE_URL_TEMPLATES`, `STORE_DISPLAY_NAMES`, `STORE_COLORS`
3. Register in `scrapers/__init__.py` (`BROWSER_SCRAPERS` or `HTTP_SCRAPERS`)
4. Deploy + restart hermes

## Local Dev

```bash
pip install -r requirements.txt
playwright install chromium
python tests/test_all.py
python agent_api.py db-stats
```

## OCI VM Notes

- 1 GB RAM micro instance. Playwright peak ~280 MB, hermes ~131 MB at rest.
- After memory pressure: OCI `RESET` to clear, then add 2 GB swap.
- OCI serial console needs RSA public key (ed25519 rejected).
- Python venv: `/home/ubuntu/precosbot/venv/bin/python`

## OCI API Key

```ini
tenancy_ocid=ocid1.tenancy.oc1..aaaaaaaa5vfmx4xoxmfv577ibav5fk3ablvy56yo4arls7lvyrtbvcsohjha
user_ocid=ocid1.user.oc1..aaaaaaaagx367raaxizktk2dzvwhirftnwhcpsm72gw5iblbwqwpwpwktl3a
fingerprint=04:73:54:2c:b2:2b:4d:77:b7:f3:d9:17:02:3f:43:44
region=sa-saopaulo-1
ssh_public_key_path=/c/Users/samue/.ssh/oci_yvy.pub
private_key_path=/c/Users/samue/.ssh/oci_yvy
```
