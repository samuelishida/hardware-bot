"""
db/queries.py — Backward compatibility layer.

Re-exports from new repository modules for legacy imports.
New code should import from db.repositories directly.
"""

from __future__ import annotations

# Re-export everything from repositories for backward compatibility
from db.repositories import (
    PriceRecord,
    insert_price,
    get_latest_by_store,
    get_all_latest,
    get_price_history,
    get_historical_min,
    get_active_alerts,
    deactivate_alert,
    set_user_alert,
    cancel_user_alert,
    get_user_alert,
    get_tracked_products,
    add_tracked_product,
    remove_tracked_product,
    get_all_tracked_products,
    is_product_tracked,
    get_tracked_product,
)

__all__ = [
    "PriceRecord",
    "insert_price",
    "get_latest_by_store",
    "get_all_latest",
    "get_price_history",
    "get_historical_min",
    "get_active_alerts",
    "deactivate_alert",
    "set_user_alert",
    "cancel_user_alert",
    "get_user_alert",
    "get_tracked_products",
    "add_tracked_product",
    "remove_tracked_product",
    "get_all_tracked_products",
    "is_product_tracked",
    "get_tracked_product",
]
