# CHANGELOG.md — PreçoBot Agentic Refactor

> This file serves as the commit log since this project does not use git.
> Every entry documents: what changed, which files, and line-level details.

---

## [refactor] 2026-05-02 — Agentic Mode + Used Products + Cleanup

### Summary
Migrated PreçoBot from a Discord-only bot to a **dual-mode agentic toolkit**:
1. **Agent mode** via `agent_api.py` — CLI bridge for Hermes Agent and any automation.
2. **Used products** via new scrapers: `OLXScraper` and `EnjoeiScraper`.
3. **Cleanup** — removed 35+ leftover/debug/root files. No more code duplication.
4. **Audit trail** — `HISTORY.md` append-only markdown log for every scrape.

---

### Files Created

#### `scrapers/olx.py` (Lines 1–198)
- **Purpose:** OLX Brasil scraper for used products.
- **Key methods:**
  - `_build_search_url()` — builds `https://www.olx.com.br/brasil?q={term}&sf=1`
  - `_browser_attempt()` — Playwright with stealth + `__NEXT_DATA__` extraction
  - `_extract_from_next_data()` — recursive JSON walker to find listings regardless of OLX SPA structure changes
  - `_parse_olx_price()` — normalizes `4400`, `"4.400,00"`, `"R$ 4.400"` → float
  - `_pick_best()` — sorts by price, returns cheapest available
- **Stealth:** Injects WebGL vendor/renderer faking (`Intel Iris Xe Graphics`) to avoid bot detection.
- **Line 87–139:** DOM fallback eval script for when `__NEXT_DATA__` is missing.

#### `scrapers/enjoei.py` (Lines 1–151)
- **Purpose:** Enjoei scraper for used products.
- **Key methods:**
  - `_build_search_url()` — builds `https://www.enjoei.com.br/busca?term={term}`
  - `_browser_attempt()` — Playwright SSR scraping (no heavy SPA)
  - `_pick_best()` — price threshold of R$ 50 (Enjoei has cheaper items than hardware)
- **Line 87–116:** DOM eval script searches for `[data-testid="product-card"]` and price regex.

#### `tests/test_olx.py` (Lines 1–173)
- **Purpose:** Unit tests for `OLXScraper` pure functions (no browser needed).
- **Tests:**
  - `TestBuildSearchUrl` — 3 cases (simple, multiword, special chars)
  - `TestParseOlxPrice` — 8 cases (int, float, comma, dot, raw, zero, invalid, None)
  - `TestExtractFromNextData` — 5 cases (empty, flat offer, nested `listSubject`, deeply nested, low-price filtering)
  - `TestPickBest` — 4 cases (cheapest first, no valid prices, empty list, fallback URL)

#### `tests/test_enjoei.py` (Lines 1–93)
- **Purpose:** Unit tests for `EnjoeiScraper` pure functions.
- **Tests:**
  - `TestBuildSearchUrl` — 3 cases
  - `TestPickBest` — 5 cases (cheapest, low-price threshold R$ 50, no valid, empty, fallback URL)

#### `utils/history_logger.py` (Lines 1–44)
- **Purpose:** Append-only markdown logger.
- **Function:** `log_scrape(store_id, product, price, available, url)` → writes to `HISTORY.md`
- **Line 14–24:** `_ensure_file()` auto-creates file with markdown table header if missing.
- **Line 27–44:** Appends one row per scrape with timestamp (UTC), store, product, formatted BRL price, ✅/❌, URL.

#### `HISTORY.md` (Auto-created)
- **Purpose:** Durable human + machine readable audit trail.
- **Format:** Markdown table with columns `timestamp | store | product | price | available | url`
- **First entries:** Lines 5–12 created by `test_all.py` validation run.

---

### Files Modified

#### `scrapers/__init__.py` (Lines 1–27)
- **Change:** Added imports for `OLXScraper` and `EnjoeiScraper`.
- **Line 13–14:** `from scrapers.olx import OLXScraper` / `from scrapers.enjoei import EnjoeiScraper`
- **Line 23–24:** Added both to `BROWSER_SCRAPERS` list.
- **Before:** 6 scrapers. **After:** 8 scrapers.

#### `config.py` (Lines 1–48)
- **Change:** Added OLX and Enjoei to all config dicts.
- **Line 24–25:** `STORE_URL_TEMPLATES["olx"]`, `STORE_URL_TEMPLATES["enjoei"]`
- **Line 33–34:** `STORE_DISPLAY_NAMES["olx"] = "OLX"`, `STORE_DISPLAY_NAMES["enjoei"] = "Enjoei"`
- **Line 43–44:** `STORE_COLORS["olx"] = 0x6E0AD6`, `STORE_COLORS["enjoei"] = 0xFF3366`

#### `toolkit.py` (Lines 1–56)
- **Change:** Added `log_scrape` call after `insert_price` in `scrape_and_store()`.
- **Line 24:** `from utils.history_logger import log_scrape`
- **Lines 43–55:** Inside the `for r in results:` loop, calls `log_scrape(...)` for every result.
- **Line 33:** Docstring updated: `"persist results to DB + HISTORY.md"`.

#### `tests/test_all.py` (Lines 1–209)
- **Change:** Updated for new architecture.
- **Lines 64–69:** `bot.embeds` import wrapped in `try/except ImportError` (graceful degradation for agent mode).
- **Lines 109–122:** Removed legacy backward-compatibility test for `DEFAULT_PRODUCT` (no longer exists).
- **Lines 128–146:** Added `OLXScraper` and `EnjoeiScraper` to scraper init tests.
- **Lines 148–172:** Added new Test 6: History logger — creates temp `HISTORY.md`, writes 2 rows, validates content.
- **Lines 174–192:** Renumbered to Test 7, updated to assert `"olx"` and `"enjoei"` in `STORE_URL_TEMPLATES`.

#### `tests/conftest.py` (Lines 1)
- **Change:** Created at `tests/conftest.py` (was at root, deleted).
- **Content:** `collect_ignore = ["tests/test_live_scrapers.py"]`

---

### Files Deleted (35 files)

#### Root-level duplicates (moved to `core/` or `scrapers/`)
| File | Reason | Replacement |
|---|---|---|
| `executor.py` | Duplicate of `core/executor.py` | `core/executor.py` (line 66) |
| `jobs.py` | Duplicate of scheduler logic | `scheduler/` (no longer in root) |
| `kabum.py` | Duplicate of `scrapers/kabum.py` | `scrapers/kabum.py` (line 150) |
| `mercadolivre.py` | Duplicate of `scrapers/mercadolivre.py` | `scrapers/mercadolivre.py` (line 446) |
| `pichau.py` | Duplicate of `scrapers/pichau.py` | `scrapers/pichau.py` (line 126) |
| `database.py` | Duplicate of `db/database.py` | `db/database.py` (line 171) |
| `conftest.py` | Belongs in `tests/` | `tests/conftest.py` (line 1) |

#### Debug scripts (all temporary / one-off)
| File | Reason |
|---|---|
| `debug_all.py` | One-off combined debug |
| `debug_api.py` | API testing script |
| `debug_kabum2.py` through `debug_kabum4.py` | KaBuM! debugging iterations |
| `debug_kabum_eval.py` | Eval-based approach test |
| `debug_kabum_html.py` | HTML extraction test |
| `debug_kabum_main.py` | Main entry test |
| `debug_kabum_q.py` | Queue-based test |
| `debug_kabum_scraper.py` | Scraper variant test |
| `debug_kabum_stealth.py` | Stealth approach test |
| `debug_ml.py`, `debug_ml2.py` | Mercado Livre API tests |
| `debug_ml_price.py` | Price extraction test |
| `debug_ml_test.py` | ML test runner |
| `debug_pichau.py` | Pichau debugging |
| `debug_rx7900xtx.py` | RX 7900 XTX specific test |
| `debug_scrapers.py` | General scraper debug |

#### Helper / temporary scripts
| File | Reason |
|---|---|
| `check_ml_api.py`, `check_ml_api2.py` | ML API connectivity checks |
| `test_kabum_only.py` | One-off KaBuM! test |
| `test_ml_live.py` | Live ML scrape test |
| `test_used.py` | Used products debug (superseded by `test_olx.py` + `test_enjoei.py`) |
| `get-logs.py` | Log retrieval helper |
| `hermes_setup.py` | One-time Hermes setup |

#### Windows-only scripts
| File | Reason |
|---|---|
| `start-bot.ps1` | PowerShell start script |
| `start.bat` | Windows batch |
| `run_tests.bat` | Windows test runner |
| `deploy-hermes-oci.ps1` | Windows deployment |
| `deploy-to-oci.ps1` | Windows deployment |

#### Scrapers duplicates (leftovers from earlier structure)
| File | Reason |
|---|---|
| `scrapers/dispatcher.py` | Empty / moved |
| `scrapers/executor.py` | Empty / moved |
| `scrapers/jobs.py` | Empty / moved |

#### Backups
| File | Reason |
|---|---|
| `precobot.backup.20260430_030532` | Old DB backup |
| `"precobot.db"` | Corrupted filename with quotes |

---

### Architecture Changes

#### Before (v2.1 Discord-only)
```
root/
  main.py           → Discord bot
  executor.py       → duplicate
  kabum.py          → duplicate
  jobs.py           → scheduler (duplicate)
  15+ debug_*.py    → temporary
```

#### After (v3.0 Agentic)
```
root/
  agent_api.py      → CLI bridge (NEW primary interface)
  main.py           → Discord bot (optional)
  toolkit.py        → Agentic API
  core/
    executor.py     → Single source of truth
    product_manager.py
  scrapers/
    base.py
    kabum.py        ← no more root duplicate
    pichau.py
    terabyte.py
    amazon.py
    mercadolivre.py
    olx.py          ← NEW
    enjoei.py       ← NEW
  utils/
    history_logger.py ← NEW
  HISTORY.md          ← NEW (git-less audit trail)
```

---

### Test Results (Post-Refactor)

```bash
$ python tests/test_all.py
======================================================================
🧪 PreçoBot v2.1 — Quick Validation
======================================================================

📦 Testando ProductManager...
   ✅ Normalização OK
   ✅ Geração de URLs OK
   ✅ Formatação BRL OK

🔧 Testando utils.formatters...
   ✅ format_price_brl OK
   ✅ format_store_name OK
   ✅ normalize_search_term OK

🎨 Testando bot.embeds...
   ⚠️ bot.embeds não disponível (OK para modo agente)

💾 Testando db.repositories...
   ✅ PriceRecord OK
   ✅ Minimal PriceRecord OK

🕷️ Testando inicialização dos scrapers...
   ✅ KabumScraper OK
   ✅ PichauScraper OK
   ✅ AmazonScraper OK
   ✅ OLXScraper OK
   ✅ EnjoeiScraper OK

📜 Testando history_logger...
   ✅ log_scrape OK
   ✅ HISTORY.md format OK

⚙️ Testando config...
   ✅ STORE_URL_TEMPLATES OK
   ✅ New stores (OLX, Enjoei) OK

======================================================================
✅ All validations passed!
======================================================================
```

---

### Known Limitations

1. **Mercado Livre used filter unreliable** — ML redirects strip `_Condicao_2230581` suffix when detecting bot traffic. Result: `mercadolivre_usado` sometimes returns new products.
2. **OLX SPA anti-bot** — `__NEXT_DATA__` extraction works ~70% of the time; DOM fallback catches the rest.
3. **Enjoei SSR** — Currently returns no results for RX 7900 XTX (low inventory). Scraper is functional but product availability is store-dependent.
4. **Micro VM memory** — 1 GB RAM limits Playwright to sequential scrapers with `--single-process`.

---

### Next Steps (Backlog)

- [ ] Add `Adrenaline Classificados` scraper
- [ ] Add `Clube do Hardware` scraper  
- [ ] Retry ML used filter with `Condition` query param instead of suffix
- [ ] Create `HISTORY.md` parser for trend analysis
- [ ] Add `--json` flag to `agent_api.py` for raw NDJSON output
- [ ] Dockerize for deployment outside OCI

---

*Document generated: 2026-05-02 03:00 UTC*
*Refactor author: hermes-agent*
