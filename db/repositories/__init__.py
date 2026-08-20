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
    get_history_stats,
    get_historical_min,
    clear_price_cache,
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

from .selector_repo import (
    get_override,
    upsert_override,
    record_outcome,
    invalidate_if_unreliable,
    get_all_overrides,
)

from .run_repo import (
    start_run,
    finish_run,
    get_recent_runs,
)

__all__ = [
    # Price
    "PriceRecord",
    "insert_price",
    "get_latest_by_store",
    "get_all_latest",
    "get_price_history",
    "get_history_stats",
    "get_historical_min",
    "clear_price_cache",
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
    # Selector overrides (self-healing)
    "get_override",
    "upsert_override",
    "record_outcome",
    "invalidate_if_unreliable",
    "get_all_overrides",
    # Agent runs (observabilidade MAS)
    "start_run",
    "finish_run",
    "get_recent_runs",
]
