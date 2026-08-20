"""
config.py — Store configuration and scraping constants.

No Discord or scheduler vars — this is now a pure scraping toolkit.
Credentials live in .env only if needed by specific integrations.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Price alert threshold ─────────────────────────────────────────────────────
PRICE_DROP_THRESHOLD_PCT: float = float(os.getenv("PRICE_DROP_THRESHOLD_PCT", "5"))

# ── Store URL templates (use {query} placeholder) ─────────────────────────────
STORE_URL_TEMPLATES: dict[str, str] = {
    "kabum":              "https://www.kabum.com.br/busca/{query}",
    "pichau":             "https://www.pichau.com.br/search?q={query}",
    "terabyte":           "https://www.terabyteshop.com.br/busca?str={query}",
    "amazon":             "https://www.amazon.com.br/s?k={query}",
    "olx":                "https://www.olx.com.br/brasil?q={query}&sf=1",
    "enjoei":             "https://www.enjoei.com.br/busca?term={query}",
}

STORE_DISPLAY_NAMES: dict[str, str] = {
    "kabum":              "KaBuM!",
    "pichau":             "Pichau",
    "terabyte":           "Terabyte Shop",
    "amazon":             "Amazon BR",
    "olx":                "OLX",
    "enjoei":             "Enjoei",
}

STORE_COLORS: dict[str, int] = {
    "kabum":              0xF26E1F,
    "pichau":             0x004AAD,
    "terabyte":           0xE30613,
    "amazon":             0xFF9900,
    "olx":                0x6E0AD6,
    "enjoei":             0xFF3366,
}

ALL_STORE_IDS: list[str] = list(STORE_URL_TEMPLATES.keys())
