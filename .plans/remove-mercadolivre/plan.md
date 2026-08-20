# Remove Mercado Livre, Keep OLX for Used Prices

## Context

Mercado Livre is the most fragile store in the toolkit: it is CDN-blocked from the
OCI VM IP, requires cookie persistence (`ml_cookies.json`) and stealth scripts, and
its SPA product cards do not render in Lightpanda (JS engine limitation). The
`MercadoLivreUsadoScraper`'s `_Condicao_2230581` suffix is also unreliable (stripped
by ML redirects, silently falling back to new listings).

The user wants to **remove Mercado Livre entirely** (both `MercadoLivreScraper` new
and `MercadoLivreUsadoScraper` used) and rely on **OLX** (already in the registry)
for used prices. Enjoei also remains for used coverage. No new scraper is needed —
OLX and Enjoei are already registered in `BROWSER_SCRAPERS`.

Intended outcome: ML is gone from the codebase (scraper, config, docs, tests,
cookie helpers), the toolkit still scrapes KaBuM/Pichau/Terabyte/Amazon (new) +
OLX/Enjoei (used), and all tests pass.

## Assumptions and decisions

- Decision: **Full removal** (delete `scrapers/mercadolivre.py`, `ml_export_cookies.py`,
  `ml_login_helper.py`, `ml_cookies.json`, `.env.example` ML creds, and scrub all live
  config/docs/tests references). Source: user-confirmed intent ("remove ml altogether").
- Decision: **Leave historical DB data** — existing `mercadolivre`/`mercadolivre_usado`
  rows in `precobot.db` stay (no destructive migration). Source: default (safe).
- Decision: **Update `scripts/local_precos_scraper_v2.py`** to drop the ML import
  (it would break on import once `mercadolivre.py` is deleted). Source: code @
  `scripts/local_precos_scraper_v2.py:48`.
- Decision: **Leave historical records** (`CHANGELOG.md`, `scripts/local_exports/`)
  untouched — they are past snapshots/changelogs. (`docs/lightpanda-spike.md` and
  `.plans/` contain no ML references and need no action.) Source: default.
- Decision: **No toolkit/executor logic change** — the toolkit scrapes all stores in
  `BROWSER_SCRAPERS`; removing ML from the registry is the only wiring change.
  Source: code @ `toolkit.py:13,30,36` and `agents/nodes/scraper_node.py:78-80`.
- Assumption: OLX + Enjoei already provide used coverage; no new "used" mode or
  scraper is introduced. Source: code @ `scrapers/__init__.py:13-16`.

## Files to touch

### scrapers/__init__.py
- What changes: remove ML imports and registry entries.
- Function(s): none (module-level registry).
- Data shapes: `BROWSER_SCRAPERS` loses `MercadoLivreScraper` and
  `MercadoLivreUsadoScraper`.
- Integration points: consumed by `toolkit.py` and `agents/nodes/scraper_node.py`.
- Error paths: none.

### scrapers/mercadolivre.py
- What changes: **delete file** (contains `MercadoLivreScraper` + `MercadoLivreUsadoScraper`).
- Error paths: any remaining import of this module must be removed first (see
  `scripts/local_precos_scraper_v2.py`, `tests/test_antibot.py`,
  `tests/test_live_scrapers.py`, `tests/test_scrapers.py`).

### config.py
- What changes: remove `mercadolivre` and `mercadolivre_usado` from
  `STORE_URL_TEMPLATES`, `STORE_DISPLAY_NAMES`, `STORE_COLORS`.
- Data shapes: the three dicts lose the two ML keys.
- Integration points: `core/product_manager.py:get_search_url`/`get_all_search_urls`
  iterate these dicts — no code change needed, keys just disappear.
- Error paths: `get_search_url("mercadolivre", ...)` now raises `ValueError` (already
  the contract for unknown stores).

### ml_export_cookies.py, ml_login_helper.py, ml_cookies.json
- What changes: **delete all three** (cookie export/login helpers + persisted cookies).

### .env.example
- What changes: remove the "Mercado Livre credentials" block (`ML_EMAIL`, `ML_PASSWORD`).

### .gitignore
- What changes: remove the `ml_cookies.json` line.

### README.md
- What changes: remove the two ML rows from the store table (lines 26-27); update intro
  line 3 to drop "Mercado Livre"; change the store count on line 9 from **8 → 6**
  ("busca qualquer produto em 6 lojas (novos e usados)"); remove the `ML_EMAIL`/
  `ML_PASSWORD` lines (145-146) from the `.env` example block; remove the
  "ML_EMAIL/ML_PASSWORD" auto-login note (line 153); remove the `mercadolivre.py`
  entry from the project file tree (line 212).

### AGENTS.md
- What changes: remove ML references at lines 3, 42, 154 (intro store list, scraper
  tree entry, "Mercado Livre (VM)" note).

### hermes_setup.py
- What changes: remove "Mercado Livre (new + used)" from the generated skill stores
  list (line ~120) and the "Note: Mercado Livre may be blocked from OCI IPs" line
  (line ~122).

### hermes/skills/shopping/precosbot/SKILL.md
- What changes: remove ML references (lines 65, 67, 78, 79) — store list, OCI-block
  note, and the "ML used filter unreliable" pitfall.

### hermes/tools/precosbot.py
- What changes: remove "Mercado Livre" from the `precosbot_check` description (line ~161).

### deploy-hermes-oci.ps1
- What changes: scrub ML from the embedded SKILL.md heredoc — tool description
  (line 127), `mercadolivre` tag (line 131), stores list "Mercado Livre (new + used)"
  (line 162), and the OCI-block note (line 164). Mirrors the `hermes_setup.py` edits.
- Integration points: this heredoc is what gets deployed to the VM's
  `~/.hermes/skills/shopping/precosbot/SKILL.md`; leaving it stale would re-advertise ML.

### scripts/local_precos_scraper_v2.py
- What changes: remove the `MercadoLivreScraper` import (line 48) and its entry in the
  scraper list (line ~116).

### core/browser.py
- What changes: scrub the "SPA do Mercado Livre" mention from the websocket keepalive
  comment (line ~529) — comment-only reference, but it would fail the verification rg.

### tests/test_scrapers.py
- What changes: remove `TestMercadoLivreScraper` class and the
  `from scrapers.mercadolivre import MercadoLivreScraper` import.

### tests/test_antibot.py
- What changes: remove the ML import (line 28) and the `HTTP_SCRAPERS` entry
  `("MercadoLivre", MercadoLivreScraper)` (line 58).

### tests/test_live_scrapers.py
- What changes: remove the ML import (line 24), the `HTTP_SCRAPERS` dict entry
  (line 33), and `"mercadolivre"` from the `all` order list (line 78).

### tests/test_formatters.py
- What changes: remove `test_format_mercadolivre` (lines 59-60).

### tests/test_integration.py
- What changes: remove `"mercadolivre"` from the store list in
  `test_full_product_parse_flow` (line 18).

### tests/test_product_manager.py
- What changes: remove the `ml_url` block (lines 59-61).

## Edge cases

- **Legacy script breakage**: `scripts/local_precos_scraper_v2.py` imports
  `MercadoLivreScraper`; must be updated before/with deleting `mercadolivre.py` or the
  script fails on import.
- **`get_search_url("mercadolivre", ...)`**: after removal this raises `ValueError`
  ("Loja 'mercadolivre' não suportada") — acceptable, matches unknown-store contract.
- **Historical DB rows**: `mercadolivre`/`mercadolivre_usado` rows remain in
  `price_history`; `get_history`/`get_analysis` will still show them. No code change.
- **`format_store_name("mercadolivre")`**: after removing the config key, falls back
  to `store_id.title()` → `"Mercadolivre"` (verified in `utils/formatters.py`). So
  historical `mercadolivre`/`mercadolivre_usado` rows in `get_history`/`get_analysis`
  render as "Mercadolivre"/"Mercadolivre_Usado" — acceptable per the "leave DB data"
  decision, but a conscious trade-off.
- **`scripts/local_exports/`**: contains historical `mercadolivre` rows — left as-is
  (data snapshot, not runtime).

## Verification

- Run: `PYTHONPATH=.deps python3 -m pytest tests/ -q` (expect all pass; ML test
  classes removed).
- Run: `PYTHONPATH=.deps python3 -c "from scrapers import BROWSER_SCRAPERS; print([c.store_id for c in BROWSER_SCRAPERS])"`
  → expect `['kabum', 'pichau', 'terabyte', 'amazon', 'olx', 'enjoei']` (no ML).
- Run: `PYTHONPATH=.deps python3 -c "from config import ALL_STORE_IDS; print(ALL_STORE_IDS)"`
  → expect no `mercadolivre`/`mercadolivre_usado`.
- Run: `rg -n "mercadolivre|MercadoLivre|Mercado Livre|ml_cookies|ml_export_cookies|ml_login_helper|ML_EMAIL|ML_PASSWORD|Condicao_2230581" --glob '!CHANGELOG.md' --glob '!scripts/local_exports/**' .`
  → expect no live-code matches (covers both "Mercado Livre" and "mercadolivre" spellings).
- Tests to add/update: none new; existing ML tests removed.
- Manual: `python agent_api.py check "rtx 4060"` → confirm OLX/Enjoei still return
  used results and no ML store appears.
- Done criteria: no live-code reference to Mercado Livre remains; OLX/Enjoei still
  provide used prices; full test suite passes.

## Standards / common-mistakes referenced

- `.agents/learnings/mas-review-fixes.md` — "Reuse" notes that legacy scripts
  (`scripts/local_precos_scraper*.py`) are standalone and were deliberately kept;
  update rather than delete where feasible.

## Estimated scope

S

## Open questions (CONSIDER from review)

- Historical `mercadolivre`/`mercadolivre_usado` rows will render as
  "Mercadolivre"/"Mercadolivre_Usado" (via `store_id.title()` fallback) in
  `get_history`/`get_analysis` — accepted per the "leave DB data" decision; noted in
  Edge cases.
- `docs/lightpanda-spike.md` and `.plans/` contain no ML references — no action
  needed; removed from verification exclusions.
- No `.env` file exists in the repo (only `.env.example`) — the "delete .env ML creds"
  mention is moot; only `.env.example` is edited.

## Status

**Implemented 2026-08-19.** All verification passed:
- `PYTHONPATH=.deps python3 -m pytest tests/ -q` → **244 passed** (3 ML tests removed).
- `rg` sweep for all ML spellings → **no live-code matches**.
- `BROWSER_SCRAPERS` / `ALL_STORE_IDS` → `['kabum', 'pichau', 'terabyte', 'amazon', 'olx', 'enjoei']`.
- Deleted: `scrapers/mercadolivre.py`, `ml_export_cookies.py`, `ml_login_helper.py`, `ml_cookies.json`.
- Scrubbed: registry, config, 6 test files, README, AGENTS.md, hermes skill/tool/setup, deploy-hermes-oci.ps1, legacy script, browser comment.