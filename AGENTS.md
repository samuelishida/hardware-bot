# AGENTS.md — PreçoBot

Discord price tracker bot for Brazilian hardware stores (KaBuM, Pichau, Terabyte, Mercado Livre, Amazon BR).

## Architecture

```
main.py                     # Entry point: Discord bot + APScheduler
config.py                   # Env vars (DISCORD_TOKEN, GUILD_ID, ALERT_CHANNEL_ID, intervals)
.env                        # Secrets (never commit)
bot/
  cog_monitor.py            # Slash commands organized by group
  embeds.py                 # Discord Embed factory
core/
  product_manager.py        # Product name normalization, search URL generation
db/
  database.py               # SQLite setup (aiosqlite), async context manager
  queries.py                # Backward compat layer (re-exports from repositories/)
  repositories/             # Repository pattern by entity
    price_repo.py           # Price history operations
    alert_repo.py           # User alert operations
    tracking_repo.py        # Product tracking operations
scheduler/
  jobs.py                   # Orchestration: scrape + alert pipeline
  executor.py               # Scraper execution engine (browser lifecycle)
  dispatcher.py             # Alert dispatch (channel + DM)
scrapers/
  base.py                   # BaseScraper, ScrapeResult dataclass
  kabum.py                  # KaBuM! scraper (Playwright)
  pichau.py                 # Pichau scraper (Playwright)
  terabyte.py               # Terabyte scraper (Playwright)
  amazon.py                 # Amazon BR scraper (Playwright)
  mercadolivre.py           # Mercado Livre scraper (HTTP API + Playwright fallback)
utils/
  formatters.py             # Shared formatting utilities
tests/
  test_all.py               # Quick validation
  test_formatters.py        # Formatter tests
  test_product_manager.py   # ProductManager tests
  test_repositories.py      # Repository tests
  test_executor.py          # Executor tests
  test_embeds.py            # Embed tests
  test_integration.py       # Integration tests
```

## Key Patterns

- **Scrapers**: Subclass `BaseScraper`, implement `async scrape() -> ScrapeResult`. Use `browser` kwarg for Playwright-based scrapers. `MercadoLivreScraper` is browser-only (Playwright with stealth + cookie persistence via `ml_cookies.json`).
- **Scraper instantiation**: ALWAYS use keyword args: `cls(browser=b, search_term=term)`. Never positional — `browser` and `search_term` can swap.
- **MercadoLivreScraper**: `_scrape_via_browser()` creates its own Playwright instance independently (does NOT use `self.browser`). Owns its lifecycle in try/finally.
- **Scheduler**: Uses APScheduler `interval` trigger with `minutes=SCRAPE_INTERVAL_MINUTES`. Set `SCRAPE_INTERVAL_MINUTES` in `.env` (default 60).
- **Python 3.10**: VM runs 3.10. Use `from __future__ import annotations` for union type syntax (`X | Y`).
- **SQLite DB**: `precobot.db` at project root. Tables: `price_history`, `user_alerts`, `tracked_products`.

## Commands

| Command | Description |
|---------|-------------|
| `/precos` | Current prices (live fallback if DB empty) |
| `/buscar <produto>` | Live search any product |
| `/monitorar <produto>` | Track product in channel (15-min intervals) |
| `/parar <produto>` | Stop tracking |
| `/lista` | List tracked products in channel |
| `/alerta <valor>` | DM alert when price drops to target |
| `/alerta cancelar` | Cancel DM alert |
| `/historico [dias]` | Price history summary |
| `/status` | Bot status |
| `/ajuda` | Command list |

## Deployment (OCI VM)

```bash
# SSH
ssh -i ~/.ssh/oci_yvy ubuntu@137.131.245.64

# VM paths
REMOTE_DIR=/home/ubuntu/precosbot
SERVICE=precosbot.service

# Deploy single file
scp -i ~/.ssh/oci_yvy <local_file> ubuntu@137.131.245.64:$REMOTE_DIR/<path>
ssh -i ~/.ssh/oci_yvy ubuntu@137.131.245.64 "sudo systemctl restart precosbot"

# Deploy multiple files
scp -i ~/.ssh/oci_yvy bot/cog_monitor.py ubuntu@137.131.245.64:$REMOTE_DIR/bot/
scp -i ~/.ssh/oci_yvy scrapers/mercadolivre.py ubuntu@137.131.245.64:$REMOTE_DIR/scrapers/
ssh -i ~/.ssh/oci_yvy ubuntu@137.131.245.64 "sudo systemctl restart precosbot"

# Full deploy (all files)
cd e:\Code\Scripts\precosbot
scp -i ~/.ssh/oci_yvy config.py main.py requirements.txt ubuntu@137.131.245.64:$REMOTE_DIR/
scp -i ~/.ssh/oci_yvy bot/*.py ubuntu@137.131.245.64:$REMOTE_DIR/bot/
scp -i ~/.ssh/oci_yvy core/*.py ubuntu@137.131.245.64:$REMOTE_DIR/core/
scp -i ~/.ssh/oci_yvy db/*.py ubuntu@137.131.245.64:$REMOTE_DIR/db/
scp -i ~/.ssh/oci_yvy db/repositories/*.py ubuntu@137.131.245.64:$REMOTE_DIR/db/repositories/
scp -i ~/.ssh/oci_yvy scheduler/*.py ubuntu@137.131.245.64:$REMOTE_DIR/scheduler/
scp -i ~/.ssh/oci_yvy scrapers/*.py ubuntu@137.131.245.64:$REMOTE_DIR/scrapers/
scp -i ~/.ssh/oci_yvy utils/*.py ubuntu@137.131.245.64:$REMOTE_DIR/utils/
ssh -i ~/.ssh/oci_yvy ubuntu@137.131.245.64 "sudo systemctl restart precosbot"

# Logs
journalctl -u precosbot -f                     # Follow logs
journalctl -u precosbot -n 100 --no-pager       # Last 100 lines
sudo systemctl restart precosbot                 # Restart bot
sudo systemctl status precosbot                  # Status

```

## Windows / OCI Recovery

- On Windows, prefer Python `paramiko` over OpenSSH when private-key ACLs block `ssh -i`.
- If OCI shows the VM as `RUNNING` but SSH banner exchange times out, the micro VM is likely under memory pressure rather than powered off.
- Use OCI `RESET` to clear a wedged boot/sshd state, then reconnect and add swap.
- After recovery on a 1 GB micro instance, create a 2 GB swapfile and persist it in `/etc/fstab`.
- OCI serial console creation needs an RSA public key; `ssh-ed25519` keys are rejected.

```

# DB inspection
ssh ... "cd $REMOTE_DIR && venv/bin/python -c \"
import sqlite3, json
db = sqlite3.connect('precobot.db')
db.row_factory = sqlite3.Row
for r in db.execute('SELECT * FROM price_history ORDER BY id DESC LIMIT 5'):
    print(dict(r))
\""

# Python on VM
/home/ubuntu/precosbot/venv/bin/python            # Venv Python 3.12
```

### systemd unit (`/etc/systemd/system/precosbot.service`)

```ini
[Unit]
Description=PrecoBot Discord Price Tracker
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/precosbot
Environment=PATH=/home/ubuntu/precosbot/venv/bin:/usr/bin
ExecStart=/home/ubuntu/precosbot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Environment (.env)

```
DISCORD_TOKEN=<bot_token>
DISCORD_GUILD_ID=<guild_id>
ALERT_CHANNEL_ID=<channel_id>    # Replace 123456789012345678 with real channel
SCRAPE_INTERVAL_MINUTES=15
PRICE_DROP_THRESHOLD_PCT=5
```

## Local Dev

```bash
pip install -r requirements.txt
playwright install chromium
python main.py
```

## Known Issues

- **Amazon/Terabyte**: Frequent timeouts/headless blocking on VM (anti-bot)
- **KaBuM**: Cards sometimes don't render in headless
- **Mercado Livre (VM)**: OCI datacenter IP is blocked at the CDN level — both `api.mercadolibre.com` (403) and `lista.mercadolivre.com.br` (login wall) are blocked. Fix: either (a) add `ML_EMAIL`/`ML_PASSWORD` to `.env` for auto-login, or (b) run `python ml_export_cookies.py` on Windows (as admin, Chrome must have ML session) and `scp ml_cookies.json` to VM. Cookies are saved to `ml_cookies.json` after each successful scrape and reused. See `.env.example` for details.
- **Pichau**: Often returns "not found" for niche products
- **ALERT_CHANNEL_ID**: Currently placeholder `123456789012345678` — replace with real channel ID
- **`/buscar` 404**: If interaction expires before `defer()` (3s), handled with try/except on `discord.errors.NotFound`
- **Micro VM CPU / memory pressure**: `VM.Standard.E2.1.Micro` (1 OCPU, 1GB RAM) can become SSH-unresponsive while still reporting `RUNNING`. Add swap after recovery and use OCI `RESET` if the shell hangs.

## Lint/Typecheck

No linter configured. Python 3.12 target (Ubuntu 24.04). Use `from __future__ import annotations` for `X | Y` type syntax.

## OCI API Key

```ini
# OCI API Key
tenancy_ocid=ocid1.tenancy.oc1..aaaaaaaa5vfmx4xoxmfv577ibav5fk3ablvy56yo4arls7lvyrtbvcsohjha
user_ocid=ocid1.user.oc1..aaaaaaaagx367raaxizktk2dzvwhirftnwhcpsm72gw5iblbwqwpwpwktl3a
fingerprint=04:73:54:2c:b2:2b:4d:77:b7:f3:d9:17:02:3f:43:44

region=sa-saopaulo-1
compartment_ocid=ocid1.tenancy.oc1..aaaaaaaa5vfmx4xoxmfv577ibav5fk3ablvy56yo4arls7lvyrtbvcsohjha

# SSH keys (file paths, not key content)
ssh_public_key_path=/c/Users/samue/.ssh/oci_yvy.pub
private_key_path=/c/Users/samue/.ssh/oci_yvy
```