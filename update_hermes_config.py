#!/usr/bin/env python3
import yaml
from pathlib import Path

config_path = Path.home() / ".hermes" / "config.yaml"
config = yaml.safe_load(config_path.read_text()) or {}

config["model"] = {
    "base_url": "http://localhost:11434/v1",
    "default": "deepseek-v4-flash:cloud",
    "provider": "auto",
}
config.setdefault("streaming", {})["enabled"] = True

config_path.write_text(yaml.dump(config, default_flow_style=False, allow_unicode=True))
print("config.yaml updated: ollama / deepseek-v4-flash:cloud")
