"""
utils/formatters.py — Shared formatting utilities.

Centralizes all formatting logic used across scrapers, embeds, and commands.
"""

from __future__ import annotations


def format_price_brl(price: float | None) -> str:
    """Format a price as Brazilian Real (R$ 1.234,56)."""
    if price is None:
        return "Indisponível"
    return f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_store_name(store_id: str) -> str:
    """Get display name for a store ID."""
    from config import STORE_DISPLAY_NAMES
    return STORE_DISPLAY_NAMES.get(store_id, store_id.title())


def normalize_search_term(term: str) -> str:
    """
    Normalize a product search term for URLs.
    
    Examples:
        "RTX 4060 Ti" → "rtx-4060-ti"
        "iPhone 15 Pro" → "iphone-15-pro"
    """
    return term.lower().strip().replace(" ", "-")
