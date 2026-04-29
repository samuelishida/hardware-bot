"""
scheduler/jobs.py — Periodic scrape job orchestration.

Coordinates the scraping pipeline using executor and dispatcher modules.
"""

from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING

from config import ALERT_CHANNEL_ID, DEFAULT_PRODUCT, DEFAULT_SEARCH_TERM
from scrapers.kabum import KabumScraper
from scrapers.pichau import PichauScraper
from scrapers.terabyte import TeraScraper
from scrapers.amazon import AmazonScraper
from scrapers.mercadolivre import MercadoLivreScraper, MercadoLivreUsadoScraper
from db.repositories import get_latest_by_store, insert_price, get_active_alerts, get_all_tracked_products
from db.database import acquire_lock, release_lock
from scheduler.executor import scrape_product
from scheduler.dispatcher import dispatch_user_alerts

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)

# Scraper classifications
BROWSER_SCRAPERS = [KabumScraper, PichauScraper, TeraScraper]
HTTP_SCRAPERS = [AmazonScraper, MercadoLivreScraper, MercadoLivreUsadoScraper]


async def run_scrape_job(bot: "discord.Client") -> None:
    """
    Main scrape job — called by APScheduler at configured intervals.
    
    Flow:
    1. Acquire lock (prevent duplicate runs)
    2. Scrape default product (backward compatibility)
    3. Save results and detect price changes
    4. Dispatch channel alerts (price drop, restock)
    5. Dispatch user DM alerts
    6. Process tracked products per channel
    7. Release lock
    """
    # Try to acquire lock - if fails, another instance is running
    if not await acquire_lock("scrape_job", ttl_minutes=10):
        logger.warning("Varredura já em execução. Pulando.")
        return
    
    logger.info("Iniciando varredura de preços...")
    
    try:
        channel = bot.get_channel(ALERT_CHANNEL_ID)
        if channel is None:
            logger.warning(
                f"Canal {ALERT_CHANNEL_ID} não encontrado. Seguindo sem alertas no canal."
            )

        # ── Step 1: Scrape default product ─────────────────────────────────────
        results = await scrape_product(BROWSER_SCRAPERS, HTTP_SCRAPERS, DEFAULT_SEARCH_TERM)
        logger.info(f"Varredura concluída: {len(results)}/{len(BROWSER_SCRAPERS) + len(HTTP_SCRAPERS)} scrapers OK.")

        # ── Step 2 & 3: Save results and send channel alerts ───────────────────
        for result in results:
            previous = await get_latest_by_store(result.store_id, product_name=DEFAULT_PRODUCT)
            
            await insert_price(
                store_id=result.store_id,
                price=result.price,
                available=result.available,
                stock_label=result.stock_label,
                url=result.url,
                product_name=DEFAULT_PRODUCT,
                search_term=DEFAULT_SEARCH_TERM,
            )

            previous_price = previous.price if previous else None
            from scheduler.dispatcher import process_price_result
            await process_price_result(result, previous_price, channel, product_name=DEFAULT_PRODUCT)

        # ── Step 4: Dispatch user DM alerts ─────────────────────────────────────
        active_alerts = await get_active_alerts()
        await dispatch_user_alerts(bot, active_alerts, results, default_product_name=DEFAULT_PRODUCT)

        # ── Step 5: Process tracked products ────────────────────────────────────
        tracked = await get_all_tracked_products()
        if tracked:
            logger.info(f"Varrendo {len(tracked)} produto(s) monitorado(s)...")
            
            # Parallel scrape all tracked products
            tp_tasks = [
                scrape_product(BROWSER_SCRAPERS, HTTP_SCRAPERS, tp["search_term"])
                for tp in tracked
            ]
            all_tp_results = await asyncio.gather(*tp_tasks)
            
            for tp, tp_results in zip(tracked, all_tp_results):
                tp_name = tp["product_name"]
                tp_channel_id = tp["channel_id"]

                # Save all results
                for result in tp_results:
                    await insert_price(
                        store_id=result.store_id,
                        price=result.price,
                        available=result.available,
                        stock_label=result.stock_label,
                        url=result.url,
                        product_name=tp_name,
                        search_term=tp["search_term"],
                    )

                # Dispatch user DM alerts for this tracked product
                await dispatch_user_alerts(bot, active_alerts, tp_results, default_product_name=tp_name)

                # Send summary to channel
                tp_channel = bot.get_channel(int(tp_channel_id))
                if tp_channel is not None and tp_results:
                    from bot.embeds import make_prices_table_embed
                    embed = make_prices_table_embed(tp_results, product_name=tp_name)
                    embed.set_footer(text="PreçoBot · Monitoramento automático")
                    try:
                        await tp_channel.send(embed=embed)
                    except Exception as e:
                        logger.warning(f"Falha ao enviar no canal {tp_channel_id}: {e}")
        
        logger.info("Varredura finalizada com sucesso.")
    
    except Exception as e:
        logger.error(f"Erro na varredura: {e}", exc_info=True)
    
    finally:
        await release_lock("scrape_job")
