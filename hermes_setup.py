#!/usr/bin/env python3
"""
hermes_setup.py — Run on OCI VM to configure hermes for precosbot integration.
Usage: python3 hermes_setup.py
"""
import sys
import yaml
from pathlib import Path

HERMES_DIR = Path.home() / ".hermes" / "hermes-agent"
PRECOSBOT_PATH = "/home/ubuntu/precosbot"

def patch_toolsets():
    toolsets_path = HERMES_DIR / "toolsets.py"
    if not toolsets_path.exists():
        print(f"WARNING: {toolsets_path} not found")
        return

    content = toolsets_path.read_text()
    if "precosbot_check" in content:
        print("toolsets.py already patched")
        return

    old = (
        '    "kanban_show", "kanban_complete", "kanban_block", "kanban_heartbeat",\n'
        '    "kanban_comment", "kanban_create", "kanban_link",\n'
        ']'
    )
    new = (
        '    "kanban_show", "kanban_complete", "kanban_block", "kanban_heartbeat",\n'
        '    "kanban_comment", "kanban_create", "kanban_link",\n'
        '    # PrecosBot - Brazilian e-commerce price tracking (gated via check_fn)\n'
        '    "precosbot_check", "precosbot_latest", "precosbot_history",\n'
        '    "precosbot_list_tracked", "precosbot_db_stats",\n'
        ']'
    )

    if old in content:
        toolsets_path.write_text(content.replace(old, new))
        print("toolsets.py patched OK")
    else:
        print("WARNING: kanban marker not found - appending to _HERMES_CORE_TOOLS manually")
        # Fallback: insert before the closing ]
        idx = content.rfind("]")
        if idx > 0:
            insert = (
                '    # PrecosBot - Brazilian e-commerce price tracking (gated via check_fn)\n'
                '    "precosbot_check", "precosbot_latest", "precosbot_history",\n'
                '    "precosbot_list_tracked", "precosbot_db_stats",\n'
            )
            content = content[:idx] + insert + content[idx:]
            toolsets_path.write_text(content)
            print("toolsets.py patched (fallback method)")


def setup_config():
    config_path = Path.home() / ".hermes" / "config.yaml"
    config_path.parent.mkdir(exist_ok=True)

    config = {}
    if config_path.exists():
        try:
            config = yaml.safe_load(config_path.read_text()) or {}
        except Exception:
            config = {}

    config.setdefault("skills", {})
    config["skills"].setdefault("config", {})
    config["skills"]["config"].setdefault("precosbot", {})
    config["skills"]["config"]["precosbot"]["path"] = PRECOSBOT_PATH

    config_path.write_text(yaml.dump(config, default_flow_style=False, allow_unicode=True))
    print(f"config.yaml: skills.config.precosbot.path = {PRECOSBOT_PATH}")


def install_skill():
    skill_dir = Path.home() / ".hermes" / "skills" / "shopping" / "precosbot"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"

    skill_content = """\
---
name: precosbot
description: "Check and track product prices across Brazilian e-commerce stores."
version: 1.0.0
metadata:
  hermes:
    tags: [prices, shopping, brazil, e-commerce]
    category: shopping
    config:
      - key: precosbot.path
        description: Path to the precosbot repository
        default: "/home/ubuntu/precosbot"
        prompt: "PrecoBot repository path"
---

# PrecoBot - Brazilian Price Tracker

You have tools to check prices across Brazilian e-commerce stores.

## Tools

| Tool | Speed | Use When |
|------|-------|----------|
| `precosbot_check` | 30-120s | User wants live current prices |
| `precosbot_latest` | instant | User wants last cached scan |
| `precosbot_history` | instant | User asks about price trends |
| `precosbot_list_tracked` | instant | User asks what is being monitored |
| `precosbot_db_stats` | instant | User asks about data coverage |

## Workflow

1. For "price of X?" - call `precosbot_latest` first (instant).
   If stale/missing, warn user scraping takes 30-120s, then call `precosbot_check`.
2. Sort results cheapest first. Flag unavailable stores.
3. Format prices in BRL: R$ 1.299,00

## Stores

Amazon BR, KaBuM!, Pichau, Terabyte Shop, Mercado Livre (new + used)

Note: Mercado Livre may be blocked from OCI IPs. Other stores are reliable.

## Language

Match user language. Price format always BRL (R$).
"""

    skill_path.write_text(skill_content)
    print(f"Skill installed: {skill_path}")


def setup_path():
    bashrc = Path.home() / ".bashrc"
    hermes_bin = HERMES_DIR / "venv" / "bin"
    path_line = f'\nexport PATH="{hermes_bin}:$PATH"  # hermes-agent\n'

    content = bashrc.read_text() if bashrc.exists() else ""
    if "hermes-agent" in content:
        print(".bashrc already has hermes PATH")
        return

    with open(bashrc, "a") as f:
        f.write(path_line)
    print(f".bashrc updated with hermes PATH: {hermes_bin}")


def verify():
    import subprocess
    hermes_bin = HERMES_DIR / "venv" / "bin" / "hermes"
    if hermes_bin.exists():
        result = subprocess.run([str(hermes_bin), "--version"], capture_output=True, text=True)
        print(f"hermes version: {result.stdout.strip() or result.stderr.strip() or 'OK (no version output)'}")
    else:
        print(f"WARNING: hermes binary not found at {hermes_bin}")

    # Test precosbot tool import
    precosbot_tool = HERMES_DIR / "tools" / "precosbot.py"
    if precosbot_tool.exists():
        print(f"precosbot tool: OK ({precosbot_tool})")
    else:
        print(f"WARNING: precosbot tool missing at {precosbot_tool}")

    # Test agent_api
    agent_api = Path(PRECOSBOT_PATH) / "agent_api.py"
    if agent_api.exists():
        print(f"agent_api.py: OK ({agent_api})")
    else:
        print(f"WARNING: agent_api.py missing at {agent_api}")


if __name__ == "__main__":
    print("=== Hermes PrecoBot Setup ===")
    patch_toolsets()
    setup_config()
    install_skill()
    setup_path()
    verify()
    print("\nSetup complete!")
    print(f"Run: source ~/.bashrc && hermes")
