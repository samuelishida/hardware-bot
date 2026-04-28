"""
scheduler/dispatcher.py — Alert dispatcher.

Handles sending price drop, restock, and user alert notifications.
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from config import PRICE_DROP_THRESHOLD_PCT, DEFAULT_PRODUCT
from bot.embeds import make_price_drop_embed, make_restock_embed, make_user_alert_embed
from scrapers.base import ScrapeResult

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)


async def process_price_result(
    result: ScrapeResult,
    previous_price: float | None,
    channel: "discord.TextChannel" | None,
    product_name: str = "Produto",
) -> None:
    """
    Process a single scrape result and send alerts if applicable.
    
    Args:
        result: The scrape result to process.
        previous_price: Previous known price for this product at this store.
        channel: Discord channel to send alerts to (None = no channel alerts).
        product_name: Name of the product being tracked.
    """
    # Price drop alert
    if previous_price and result.price and result.price < previous_price:
        drop_pct = (previous_price - result.price) / previous_price * 100
        if drop_pct >= PRICE_DROP_THRESHOLD_PCT:
            logger.info(
                f"[{result.store_id}] Queda de {drop_pct:.1f}%: "
                f"R${previous_price:.2f} → R${result.price:.2f}"
            )
            if channel is not None:
                embed = make_price_drop_embed(result, previous_price, drop_pct, product_name=product_name)
                await channel.send(embed=embed)

    # Restock alert
    if result.available and result.price is not None and previous_price is None:
        logger.info(f"[{result.store_id}] Disponibilidade detectada: R${result.price}")
        if channel is not None:
            embed = make_restock_embed(result, product_name=product_name)
            await channel.send(embed=embed)


async def dispatch_user_alerts(
    bot: "discord.Client",
    active_alerts: list[dict],
    valid_results: list[ScrapeResult],
    default_product_name: str = DEFAULT_PRODUCT,
) -> None:
    """
    Check and dispatch user price alerts.
    
    Args:
        bot: Discord bot client.
        active_alerts: List of active user alerts from database.
        valid_results: List of valid scrape results.
        default_product_name: Default product name for legacy alerts.
    """
    if not active_alerts:
        return

    # Build a map of store_id -> best result
    available_prices = {
        r.store_id: r for r in valid_results
        if r.available and r.price is not None
    }
    
    best_price = min(
        (r.price for r in available_prices.values()),
        default=None,
    )
    
    if best_price is None:
        return

    for alert in active_alerts:
        if best_price > alert["target_price"]:
            continue

        # Find the best store that satisfies this alert
        triggering = min(
            (r for r in available_prices.values() if r.price <= alert["target_price"]),
            key=lambda r: r.price,
            default=None,
        )
        if triggering is None:
            continue

        try:
            user = await bot.fetch_user(int(alert["discord_user"]))
            product_name = alert.get("product_name") or default_product_name
            embed = make_user_alert_embed(triggering, alert["target_price"], product_name=product_name)
            await user.send(embed=embed)
            logger.info(f"Alerta de usuário {alert['discord_user']} disparado: R${triggering.price}")
            from db.repositories import deactivate_alert
            await deactivate_alert(alert["discord_user"])
        except Exception as e:
            logger.warning(f"Falha ao enviar DM para {alert['discord_user']}: {e}")
