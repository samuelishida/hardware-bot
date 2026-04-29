"""
config.py — carrega variáveis de ambiente e define constantes globais.
Copilot: não altere esta estrutura; adicione novas variáveis seguindo o padrão abaixo.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Discord ────────────────────────────────────────────────────────────────────
DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]
DISCORD_GUILD_ID: int = int(os.environ["DISCORD_GUILD_ID"])
ALERT_CHANNEL_ID: int = int(os.environ["ALERT_CHANNEL_ID"])

# ── Scheduler ─────────────────────────────────────────────────────────────────
SCRAPE_INTERVAL_MINUTES: int = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "60"))

# ── Lógica de alerta ──────────────────────────────────────────────────────────
# Dispara alerta se o preço cair X% em relação ao último preço salvo
PRICE_DROP_THRESHOLD_PCT: float = float(os.getenv("PRICE_DROP_THRESHOLD_PCT", "5"))

# ── URLs de busca por loja (templates com {query}) ────────────────────────────
# Use {query} como placeholder para o termo de busca normalizado
STORE_URL_TEMPLATES: dict[str, str] = {
    "kabum":              "https://www.kabum.com.br/busca/{query}",
    "pichau":             "https://www.pichau.com.br/search?q={query}",
    "terabyte":           "https://www.terabyteshop.com.br/busca?str={query}",
    "mercadolivre":       "https://lista.mercadolivre.com.br/{query}",
    "mercadolivre_usado": "https://lista.mercadolivre.com.br/{query}_CONDICION_2230581",
    "amazon":             "https://www.amazon.com.br/s?k={query}",
}

# ── Cores dos embeds por loja (hex) ───────────────────────────────────────────
STORE_COLORS: dict[str, int] = {
    "kabum":              0xF26E1F,
    "pichau":             0x004AAD,
    "terabyte":           0xE30613,
    "mercadolivre":       0xFFE600,
    "mercadolivre_usado": 0xC8A800,
    "amazon":             0xFF9900,
}

STORE_DISPLAY_NAMES: dict[str, str] = {
    "kabum":              "KaBuM!",
    "pichau":             "Pichau",
    "terabyte":           "Terabyte Shop",
    "mercadolivre":       "Mercado Livre",
    "mercadolivre_usado": "Mercado Livre (Usado)",
    "amazon":             "Amazon BR",
}

# ── Produto padrão (backward compatibility) ──────────────────────────────────
PRODUCT_NAME: str = os.getenv("PRODUCT_NAME", "AMD Ryzen 5 5700X3D")
PRODUCT_SEARCH_TERM: str = os.getenv("PRODUCT_SEARCH_TERM", "ryzen-5-5700x3d")

# Aliases for refactored modules
DEFAULT_PRODUCT: str = PRODUCT_NAME
DEFAULT_SEARCH_TERM: str = PRODUCT_SEARCH_TERM

# ── URLs de busca por loja (compat) ──────────────────────────────────────────
# Alias para STORE_URL_TEMPLATES com o termo de busca padrão preenchido
STORE_URLS: dict[str, str] = {
    store_id: template.format(query=PRODUCT_SEARCH_TERM)
    for store_id, template in STORE_URL_TEMPLATES.items()
}
