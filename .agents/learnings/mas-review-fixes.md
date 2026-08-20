# MAS Review & Fixes

## Context
Reviewed a 48-file PR adding a Multi-Agent System (LangGraph + Ollama) to PreçoBot
(scraper→analyst→deal pipeline, self-healing selectors, FastMCP server, agent_runs
observability), then implemented all review findings.

## Hardest decision
Whether the langgraph `_wrap_node` in-place mutation (`state.setdefault("errors", []).append(err)`)
loses errors. The research specialist flagged it as a real bug, but empirical testing
proved it a FALSE POSITIVE: with a plain `dict` schema mutations do NOT propagate, but
with a `TypedDict` schema (which the orchestrator uses via `_GraphState`) they DO.
Lesson: verify langgraph state mutation behavior empirically — never trust static
analysis on it. `test_partial_status_when_validated_with_errors` is the guard.

## Alternatives rejected
- Deleting `scripts/local_precos_scraper.py` v1 — kept it (distinct DB-backed
  implementation), cleaned dead imports instead.
- Replacing `options.num_predict` with `max_tokens` — sent BOTH (top-level `max_tokens`
  + `options.num_predict` for backward compat with Ollama).
- Tightening the loose `langgraph>=0.2.0` pin (installed 1.2.11) — left as a NOTE;
  pinning could break the VM's installed version.
- Removing the `history_avg is None` branch in `deal_node.py` — the simplification
  specialist called it dead, but it's reachable when `analysis` lacks `avg_price_validated`.
  Restored it; the specialist was wrong.

## Least confident
- The `max_tokens` fix (C4) was never verified against a live Ollama call — only unit
  tests. Needs a real `/v1/chat/completions` smoke test.
- `_finish_run` only persists `error` for `status=="error"`, not `"partial"` — partial
  runs lose their error detail in `agent_runs`.
- Test coverage gaps: `_wrap_node` timeout branch, `_safe_update` analyst/deal branches,
  `_parse_json_lenient` fence-stripping, `agent-traces` CLI command.

## Reuse
Read before touching `agents/orchestrator.py` (state mutation), `agents/nodes/deal_node.py`
(baseline/mention handling), `agents/llm.py` (Ollama payload), or `agent_api.py` (CLI
days parsing). The `_split_days` helper in `agent_api.py` is the pattern for CLI args
that must not corrupt digit-ending product names.
