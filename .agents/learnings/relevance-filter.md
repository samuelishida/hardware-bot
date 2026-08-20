# Relevance filter & self-healing (implemented 2026-08-19)

## Context
Implemented `.plans/relevance-filter/plan.md` across 6 increments (284 tests green):
title plumbing, shared relevance module, all-6-scraper filter, analyst relevance gate,
self-healing learning of exclusions, persistence + observability.

## Golden questions

### 1. What did I learn about the system?
- `ScrapeResult` had NO title field — scrapers extracted the matched name internally
  but discarded it, so the analyst could only judge price+URL, never relevance. The
  root cause of "PS5 → Adaptador USB Sony PS Link" was the missing title, not the
  exclusion lists (Amazon had rich `SYSTEM_EXCLUSIONS`, KaBuM/Pichau only PC terms).
- OLX/Enjoei `_pick_best` is **sync**; DB access (`get_terms`) must happen in the
  async `scrape()`/`_browser_attempt()` and be passed as an arg (async-in-sync gotcha).
- `ACCESSORY_TERMS` consolidating Amazon's aggressive `SYSTEM_EXCLUSIONS` (fonte,
  gabinete, cooler, pasta térmica, ...) across all stores introduces **over-filtering
  risk**: a user legitimately searching "fonte corsair" or "gabinete nzxt" would be
  filtered. MUST-FIX: `is_relevant` must skip the accessory-term check when the
  `search_term` itself contains that term.

### 2. What would I do differently?
- MOVE fast, but VERIFY the review's MUST-FIXes into the plan *before* implementing:
  the review-plan identified the "skip accessory term present in search_term" MUST-FIX
  that is easy to miss. It was baked into `is_relevant` at implementation, but had
  the plan not been reviewed, over-filtering would have shipped.
- Test fake browsers need `page.context = context` set AND `context.close`/`context.new_page`
  as `AsyncMock` — the MagicMock default breaks `await` and silently fails.

### 3. What should the next agent know?
- `scrapers/relevance.py` (`is_relevant` + `ACCESSORY_TERMS`) is the shared filter;
  word-boundary (`\bterm\b`) prevents substring false-positives ("capa" vs "capacidade");
  diacritics normalized at runtime so ACCESSORY_TERMS must be accent-free.
- `relevance_overrides` table + `db/repositories/relevance_repo.py` (get_terms/add_term/
  get_all_terms). DB down → `[]`/no-op with log (override is optimization, never requirement).
- `agent_api.py relevance-status` lists learned terms; `scrapers/__init__.py` already has
  all 6 scrapers registered (no registry change needed).
- Full suite: `python3 -m pytest -q` (284 passed).

## Reuse
Read before touching `scrapers/relevance.py` (shared filter), any scraper's "pick best"
loop (must set `title`), `agents/nodes/analyst_node.py` (relevance gate + LLM offending_term),
`db/repositories/relevance_repo.py`, or the `agent_api.py relevance-status` command. The
`is_relevant(title, search_term, extra_terms)` signature is the API all scrapers + analyst share.
