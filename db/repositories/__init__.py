"""
db/repositories/__init__.py — Repository exports.

Provides a clean API for database operations organized by entity.
"""

from .price_repo import (
    PriceRecord,
    insert_price,
    get_latest_by_store,
    get_all_latest,
    get_price_history,
    get_historical_min,
)

from .alert_repo import (
    get_active_alerts,
    deactivate_alert,
    set_user_alert,
    cancel_user_alert,
    get_user_alert,
)

from .tracking_repo import (
    get_tracked_products,
    add_tracked_product,
    remove_tracked_product,
    get_all_tracked_products,
    is_product_tracked,
    get_tracked_product,
)

__all__ = [
    # Price
    "PriceRecord",
    "insert_price",
    "get_latest_by_store",
    "get_all_latest",
    "get_price_history",
    "get_historical_min",
    # Alerts
    "get_active_alerts",
    "deactivate_alert",
    "set_user_alert",
    "cancel_user_alert",
    "get_user_alert",
    # Tracking
    "get_tracked_products",
    "add_tracked_product",
    "remove_tracked_product",
    "get_all_tracked_products",
    "is_product_tracked",
    "get_tracked_product",
]
