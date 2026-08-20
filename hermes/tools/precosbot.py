"""
tools/precosbot.py — PreçoBot integration for hermes-agent.

Wraps the precosbot price-scraping system as hermes tools.
Requires precosbot repo path configured via:
  ~/.hermes/config.yaml:  skills.config.precosbot.path: /home/ubuntu/precosbot
  or env var:             PRECOSBOT_PATH=/home/ubuntu/precosbot

Tools exposed:
  precosbot_check        Live price scrape across BR e-commerce stores
  precosbot_latest       Cached prices from precosbot's SQLite DB
  precosbot_history      Price history over N days
  precosbot_list_tracked List products precosbot monitors automatically
  precosbot_db_stats     Database statistics
  precosbot_agent        Full multi-agent pipeline (scrape + validate + deal)
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

from tools.registry import registry


def _get_precosbot_path() -> Path | None:
    raw = os.getenv("PRECOSBOT_PATH")
    if not raw:
        try:
            import yaml
            from hermes_constants import get_hermes_home
            config_path = get_hermes_home() / "config.yaml"
            if config_path.exists():
                cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                raw = (
                    cfg.get("skills", {})
                       .get("config", {})
                       .get("precosbot", {})
                       .get("path")
                )
        except Exception:
            pass
    if not raw:
        return None
    return Path(os.path.expanduser(raw))


def _find_python(precosbot_path: Path) -> str:
    for candidate in [
        precosbot_path / "venv" / "bin" / "python",
        precosbot_path / "venv" / "bin" / "python3",
        precosbot_path / ".venv" / "bin" / "python",
    ]:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _run_api(args: list[str], timeout: int = 150) -> dict:
    path = _get_precosbot_path()
    if path is None:
        return {
            "success": False,
            "error": (
                "PreçoBot path not configured. "
                "Set skills.config.precosbot.path in ~/.hermes/config.yaml "
                "or export PRECOSBOT_PATH=/path/to/precosbot"
            ),
        }
    if not path.exists():
        return {"success": False, "error": f"PreçoBot directory not found: {path}"}

    python = _find_python(path)
    script = path / "agent_api.py"
    if not script.exists():
        return {"success": False, "error": f"agent_api.py not found in {path}"}

    try:
        proc = subprocess.run(
            [python, str(script)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(path),
        )
        if proc.returncode != 0:
            # agent_api._err() escreve o JSON de erro no stdout, não no stderr.
            if proc.stdout.strip():
                try:
                    return json.loads(proc.stdout)
                except json.JSONDecodeError:
                    pass
            stderr = proc.stderr.strip() if proc.stderr else ""
            return {"success": False, "error": stderr or "agent_api.py exited non-zero"}
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"success": False, "error": f"Invalid JSON output: {proc.stdout[:200]}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"PreçoBot timed out after {timeout}s"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _check_requirements() -> bool:
    path = _get_precosbot_path()
    return path is not None and path.exists() and (path / "agent_api.py").exists()


# ── Tool handlers ─────────────────────────────────────────────────────────────

def precosbot_check(product: str, task_id=None) -> str:
    """Live price scrape — takes 30-120s (Lightpanda browser)."""
    return json.dumps(_run_api(["check", product], timeout=150))


def precosbot_latest(product: str, task_id=None) -> str:
    """Return latest cached prices from DB (instant)."""
    return json.dumps(_run_api(["latest", product], timeout=15))


def precosbot_history(product: str, days: int = 7, task_id=None) -> str:
    """Return price history over N days from DB."""
    # agent_api.history agora usa o flag explícito `--days` (não posicional) para
    # não corromper nomes de produto que terminam em dígitos (ex.: "RTX 4060").
    return json.dumps(_run_api(["history", product, "--days", str(days)], timeout=15))


def precosbot_list_tracked(task_id=None) -> str:
    """List all products the precosbot scheduler monitors automatically."""
    return json.dumps(_run_api(["list-tracked"], timeout=10))


def precosbot_db_stats(task_id=None) -> str:
    """Return precosbot database statistics (rows, date range, size)."""
    return json.dumps(_run_api(["db-stats"], timeout=10))


def precosbot_agent(product: str, target_price: float | None = None, task_id=None) -> str:
    """Run the full multi-agent pipeline (scrape → validate → deal analysis).

    Slower than precosbot_check (adds LLM validation + deal reasoning).
    """
    args = ["agent", product]
    if target_price is not None:
        args += ["--", str(target_price)]
    return json.dumps(_run_api(args, timeout=180))


# ── Tool registration ─────────────────────────────────────────────────────────

registry.register(
    name="precosbot_check",
    toolset="precosbot",
    schema={
        "name": "precosbot_check",
        "description": (
            "Live price scrape for a product across Brazilian e-commerce stores "
            "(Amazon BR, KaBuM!, Pichau, Terabyte Shop). "
            "Launches real Lightpanda browsers — takes 30-120 seconds. "
            "Use precosbot_latest for instant cached results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product": {
                    "type": "string",
                    "description": "Product name to search (e.g. 'RTX 4070', 'Ryzen 5 5700X3D', 'SSD 1TB NVMe')",
                },
            },
            "required": ["product"],
        },
    },
    handler=lambda args, **kw: precosbot_check(args.get("product", ""), task_id=kw.get("task_id")),
    check_fn=_check_requirements,
)

registry.register(
    name="precosbot_latest",
    toolset="precosbot",
    schema={
        "name": "precosbot_latest",
        "description": (
            "Return the latest cached prices for a product from precosbot's database. "
            "Instant — no scraping. Shows prices from the last scheduled scrape cycle."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product": {
                    "type": "string",
                    "description": "Exact product name as tracked in precosbot (e.g. 'AMD Ryzen 5 5700X3D')",
                },
            },
            "required": ["product"],
        },
    },
    handler=lambda args, **kw: precosbot_latest(args.get("product", ""), task_id=kw.get("task_id")),
    check_fn=_check_requirements,
)

registry.register(
    name="precosbot_history",
    toolset="precosbot",
    schema={
        "name": "precosbot_history",
        "description": (
            "Return price history for a product over the last N days from precosbot's database. "
            "Useful for spotting price trends and historical lows."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product": {
                    "type": "string",
                    "description": "Product name to look up",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days of history to fetch (default 7, max 60)",
                    "default": 7,
                },
            },
            "required": ["product"],
        },
    },
    handler=lambda args, **kw: precosbot_history(
        args.get("product", ""), args.get("days", 7), task_id=kw.get("task_id")
    ),
    check_fn=_check_requirements,
)

registry.register(
    name="precosbot_list_tracked",
    toolset="precosbot",
    schema={
        "name": "precosbot_list_tracked",
        "description": "List all products the precosbot scheduler monitors automatically on a cron schedule.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: precosbot_list_tracked(task_id=kw.get("task_id")),
    check_fn=_check_requirements,
)

registry.register(
    name="precosbot_db_stats",
    toolset="precosbot",
    schema={
        "name": "precosbot_db_stats",
        "description": "Return precosbot database statistics: total rows, products tracked, date range, and DB file size.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: precosbot_db_stats(task_id=kw.get("task_id")),
    check_fn=_check_requirements,
)

registry.register(
    name="precosbot_agent",
    toolset="precosbot",
    schema={
        "name": "precosbot_agent",
        "description": (
            "Run the full multi-agent pipeline for a product: live scrape across "
            "Brazilian stores, LLM-assisted price validation (flags suspicious "
            "prices), and deal analysis against an optional target price. "
            "Returns validated results, a deal verdict, a summary, and the agent "
            "trace. Slower than precosbot_check (up to ~180s) — use it when the "
            "user wants a confident answer, not just raw prices."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product": {
                    "type": "string",
                    "description": "Product name to analyze (e.g. 'RTX 4070', 'Ryzen 5 5700X3D')",
                },
                "target_price": {
                    "type": "number",
                    "description": "Optional target price in BRL. If the best validated price is at or below it, the pipeline reports a deal.",
                },
            },
            "required": ["product"],
        },
    },
    handler=lambda args, **kw: precosbot_agent(
        args.get("product", ""),
        args.get("target_price"),
        task_id=kw.get("task_id"),
    ),
    check_fn=_check_requirements,
)
