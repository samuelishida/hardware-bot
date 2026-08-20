# Remove Mercado Livre (store removal)

## Context
Removed Mercado Livre entirely (both `MercadoLivreScraper` new and
`MercadoLivreUsadoScraper` used) from PreçoBot; OLX + Enjoei remain for used prices.
Deleted the scraper, cookie helpers (`ml_export_cookies.py`, `ml_login_helper.py`,
`ml_cookies.json`), and scrubbed all live references.

## Hardest decision
Whether to leave historical `mercadolivre`/`mercadolivre_usado` rows in
`precobot.db`. Chose to leave them (no destructive migration) — they render as
"Mercadolivre"/"Mercadolivre_Usado" via `format_store_name`'s `store_id.title()`
fallback. Acceptable trade-off, documented in the plan.

## Lesson: inventory ALL reference spellings before removing a store
The verification `rg` must cover every spelling of the store name, and the plan's
Files-to-touch must include **comments, docstrings, and print statements** — not just
code/config. The first sweep missed 2 references:
- a `print(f"Lojas: ... Mercado Livre")` in a legacy script
  (`scripts/local_precos_scraper_v2.py`)
- a usage docstring in `tests/test_live_scrapers.py`

Also: `deploy-hermes-oci.ps1` embeds the SKILL.md heredoc — a stale deployment
script re-advertises the removed store on the VM. Always check deploy scripts.

## Reuse
Read before removing any store/scraper or changing the scraper registry
(`scrapers/__init__.py`, `config.py`). The `rg` pattern
`mercadolivre|MercadoLivre|Mercado Livre|ml_cookies|...` (all spellings) is the
verification recipe.