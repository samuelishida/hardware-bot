# CHANGELOG.md — PreçoBot Agentic Refactor

> This file serves as the commit log since this project does not use git.
> Every entry documents: what changed, which files, and line-level details.

---

## [feature] 2026-08-19 — Migração Chrome/Playwright → Lightpanda

### Summary
Substituiu o **Playwright + Chromium** pelo **Lightpanda** (browser headless em Zig,
CDP server, pico ~123 MB vs ~280 MB do Chromium) como motor de scraping. Decisões do
usuário: apenas Lightpanda (sem fallback Playwright), remover Playwright por completo,
migrar os 8 scrapers de uma vez.

### Arquitetura

- **`core/cdp.py`** (novo) — cliente CDP mínimo sobre `websockets` (correlação
  id→resposta, `wait_event`, `on`).
- **`core/browser.py`** (novo) — facade `LightpandaBrowser`/`Context`/`Page`/
  `ElementHandle`/`Route` que espelha a superfície Playwright usada pelos scrapers.
- **`core/executor.py`** — troca `async_playwright()`/`chromium.launch` por
  `LightpandaBrowser.start()`; mesmo loop sequencial + timeout 90s.
- **Scrapers** — usam a facade (mesma forma Playwright); `:has-text()` (ML) traduzido
  para query JS por `textContent`; `Network.setBlockedURLs` usa `urlPatterns`.
- **`requirements.txt`** — remove `playwright`, adiciona `websockets>=12.0`.
- **Testes** — `tests/test_cdp.py` (10) + `tests/test_browser.py` (20) novos;
  mocks de executor/scrapers/self_healing atualizados; `tests/test_live_lightpanda.py`
  (smoke live gated por `PRECOSBOT_LIVE=1`).
- **Docs** — AGENTS.md/README.md/CHANGELOG.md atualizados; `docs/lightpanda-spike.md`
  (registro de decisão do spike).

### Spike (Inc 1) — descobertas

- Setup CDP obrigatório: `createBrowserContext → createTarget → attachToTarget`
  (sessionId em todos os comandos).
- Lightpanda suporta **1 browser context + 1 página por vez** → confirma design de
  instância compartilhada.
- `Network.setBlockedURLs` usa `urlPatterns`; `DOM.querySelector` requer
  `DOM.getDocument` antes.
- `STEALTH_SCRIPT` (APIs Chromium-only) roda sem lançar no Lightpanda.

### Deploy

- Binário Lightpanda instalado na VM (Inc 1): `/usr/local/bin/lightpanda`.
- `LIGHTPANDA_DISABLE_TELEMETRY=true` no env do hermes.
- Rollback: `git revert` + reinstalar Playwright (documentado).

---

## [feature] 2026-05-02 — Multi-Agent System (MAS): LangGraph + Ollama

### Summary
Transformed PreçoBot from a linear scraping pipeline into a **multi-agent system**:
LangGraph orchestration with specialist agents and LLM-assisted decision points
(Ollama, deterministic fallback). The LLM never vetoes a deterministic approval nor
approves a deterministic rejection; if unavailable, everything degrades to
deterministic mode.

### Architecture

```
START → scraper → analyst ─┬─(ok)──────────────→ deal → END
                           └─(re-scrape, ≤ N)──→ scraper   (feedback loop)
```

- **Scraper** — live scrape via `core/executor.py` (all stores, 1 shared browser).
- **Analyst/Validator** — validates price/availability against history; optional LLM
  for ambiguous cases.
- **Deal Hunter** — deal verdict: discount vs. historical average + optional
  `target_price`; optional LLM for the summary.
- **Self-healing** — broken selectors produce overrides in `selector_overrides`;
  "override is optimization, never a requirement" — any failure → no-op with log.
- **Observability** — each `run_agent_pipeline` writes 1 row to `agent_runs`
  (`run_repo.py`). Write failure → log, **never** propagates. Aborted runs
  (`finished_at` null) surface as `status="incomplete"` in `agent-traces`.

### Files Created

#### `agents/` (new package)
- `orchestrator.py` — LangGraph graph + `run_agent_pipeline()` (try/finally run
  recording), `_build_nodes()` (patchable), `_wrap_node()` (per-node timeout),
  `_route_after_analyst()` (feedback loop), `_build_result()`.
- `state.py` — `AgentResult` / `ValidatedPrice` / `DealResult` dataclasses.
- `config.py` — MAS env knobs (`agent_llm_mode`, `agent_max_iterations`,
  `llm_base_url`, `llm_model`, `llm_api_key`, `llm_timeout`, `llm_num_predict`);
  invalid values degrade to log + default, never raise.
- `llm.py` — Ollama OpenAI-compatible client (httpx), explicit `num_predict`.
- `self_healing.py` — selector self-healing (override é otimização, nunca requisito).
- `mcp_server.py` — MCP server (FastMCP, stdio) exposing `run_agent`, `get_latest`,
  `get_history`, `self_healing_status` as a thin facade (no new logic; error contract
  matches `agent_api`).
- `errors.py` — structured MAS errors.
- `nodes/scraper_node.py`, `nodes/analyst_node.py`, `nodes/deal_node.py` — the three
  specialist nodes (deterministic core + optional LLM).

#### `db/repositories/run_repo.py`
- `start_run(run_id, product)` — INSERT `status='running'`.
- `finish_run(run_id, status, nodes, error, duration_ms)` — UPDATE with trace JSON.
- `get_recent_runs(limit=10)` — recent runs; `finished_at` null → `status="incomplete"`.
- All wrapped in try/except → log (never raise).

### Files Modified

- `db/database.py` — additive `agent_runs` table + index; `get_db_stats()` now
  includes `agent_runs` count (degrades to 0 on old DBs).
- `db/repositories/__init__.py` — exports `start_run`, `finish_run`, `get_recent_runs`.
- `agent_api.py` — new commands `agent <product> [target_price]` and
  `agent-traces [limit]`; `db-stats` includes run count.
- `hermes/tools/precosbot.py` — new `precosbot_agent` tool (timeout 180s).
- `hermes/toolsets.py` — `precosbot_agent` in core tools.
- `hermes/skills/shopping/precosbot/SKILL.md` — `precosbot_agent` row +
  check-vs-agent guidance + MCP server section.
- `AGENTS.md`, `README.md` — "Multi-Agent System" section (architecture, env vars,
  commands, deploy, MCP server).
- `requirements.txt` — adds `langgraph>=0.2.0`, `fastmcp>=0.1.0`, `mcp>=1.0.0`.

### New env vars

| Var | Default | Descrição |
|-----|---------|-----------|
| `PRECOSBOT_AGENT_LLM` | `auto` | `auto` \| `on` \| `off` |
| `PRECOSBOT_AGENT_MAX_ITERATIONS` | `2` | Cap de re-scrapes (clamp [1,10]) |
| `PRECOSBOT_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Ollama endpoint |
| `PRECOSBOT_LLM_MODEL` | `qwen2.5:3b` | Modelo Ollama |
| `PRECOSBOT_LLM_API_KEY` | `ollama` | API key |
| `PRECOSBOT_LLM_TIMEOUT` | `60` | Timeout por chamada (s) |
| `PRECOSBOT_LLM_NUM_PREDICT` | `2048` | Máx. tokens por resposta |

### New commands

```
python agent_api.py agent <product> [target_price]   # Full MAS pipeline (30-180s)
python agent_api.py agent-traces [limit]             # Recent MAS runs (default 10)
```

### Tests
- `tests/test_orchestrator.py` — graph topology, feedback loop, iteration cap,
  error status, duration, partial status, build_graph (7).
- `tests/test_run_repo.py` — start/finish/get_recent on in-memory SQLite, error
  paths never raise (11).
- `tests/test_agent_api.py` — `agent`/`agent-traces` dispatch + arg parsing (14).
- `tests/test_mcp_server.py` — MCP tools delegate + error contract, registration (11).
- `tests/test_self_healing.py`, `tests/test_selector_repo.py` — self-healing (22).
- Full suite: **212 passed**.

### Deploy
```bash
ssh -i $SSH_KEY $VM "cd $REMOTE && git pull && pip install -r requirements.txt"
# Ollama must be running on the VM (or set PRECOSBOT_AGENT_LLM=off)
```

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
