"""
bot/cog_monitor.py — Discord slash commands cog.

Organized by command groups:
- Product commands: /precos, /buscar
- Tracking commands: /monitorar, /parar, /lista
- Alert commands: /alerta, /alerta cancelar
- System commands: /status, /ajuda, /historico
"""

from __future__ import annotations
import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import PRODUCT_NAME, PRODUCT_SEARCH_TERM, SCRAPE_INTERVAL_MINUTES, STORE_DISPLAY_NAMES
from core.product_manager import ProductManager
from db.repositories import (
    get_all_latest,
    get_price_history,
    set_user_alert,
    cancel_user_alert,
    get_tracked_products,
    add_tracked_product,
    remove_tracked_product,
    is_product_tracked,
    get_all_tracked_products,
)
from bot.embeds import (
    make_prices_table_embed,
    make_history_embed,
    make_search_results_embed,
    make_tracking_list_embed,
    make_help_embed,
)
from scheduler.executor import scrape_product
from scrapers.kabum import KabumScraper
from scrapers.pichau import PichauScraper
from scrapers.terabyte import TeraScraper
from scrapers.amazon import AmazonScraper
from scrapers.mercadolivre import MercadoLivreScraper

logger = logging.getLogger(__name__)

BROWSER_SCRAPERS = [KabumScraper, PichauScraper, TeraScraper]
HTTP_SCRAPERS = [AmazonScraper, MercadoLivreScraper]


class MonitorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pm = ProductManager()

    # ════════════════════════════════════════════════════════════════════════
    # PRODUCT COMMANDS
    # ════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="precos", description="Ver preços atuais em todas as lojas")
    @app_commands.describe(produto="Produto específico (ex: RTX 4060 Ti). Padrão: 5700X3D")
    async def cmd_precos(
        self,
        interaction: discord.Interaction,
        produto: str = None,
    ) -> None:
        """Show current prices from all stores."""
        product_name = PRODUCT_NAME
        search_term = PRODUCT_SEARCH_TERM
        
        if produto:
            product = self.pm.parse_product_name(produto)
            product_name = product.name
            search_term = product.search_term

        await interaction.response.defer()
        
        # Try database first
        records = await get_all_latest(product_name=product_name)
        
        if not records:
            # Fallback to live scrape
            await interaction.followup.send(
                "⏳ Nenhum dado em cache. Buscando preços agora...",
                ephemeral=True,
            )
            
            results = await scrape_product(BROWSER_SCRAPERS, HTTP_SCRAPERS, search_term)
            
            if not results:
                await interaction.followup.send(
                    "❌ Nenhum preço encontrado no momento. Tente novamente mais tarde.",
                    ephemeral=True,
                )
                return

            embed = make_prices_table_embed(results, product_name=product_name)
            embed.set_footer(text="PreçoBot · Busca sob demanda")
            await interaction.followup.send(embed=embed)
        else:
            embed = make_prices_table_embed(records, product_name=product_name)
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="buscar", description="Buscar preços de qualquer produto agora")
    @app_commands.describe(produto="Nome do produto (ex: RTX 4060, iPhone 15)")
    async def cmd_buscar(
        self,
        interaction: discord.Interaction,
        produto: str,
    ) -> None:
        """Search prices for a specific product across all stores."""
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            logger.warning("Interaction expired before defer")
            return
        except Exception as e:
            logger.error(f"Failed to defer interaction: {e}")
            return

        product = self.pm.parse_product_name(produto)

        try:
            msg = await interaction.followup.send(
                f"🔍 Buscando **{product.name}** (`{product.search_term}`)...",
                wait=True
            )
        except Exception as e:
            logger.error(f"Falha ao criar mensagem: {e}")
            return

        try:
            results = await scrape_product(BROWSER_SCRAPERS, HTTP_SCRAPERS, product.search_term)
        except Exception as e:
            logger.error(f"[buscar] Falha crítica na varredura: {e}", exc_info=True)
            try:
                await msg.edit(
                    content=None,
                    embed=discord.Embed(
                        title="❌ Erro interno",
                        description="Erro ao iniciar os scrapers. Tente novamente em alguns instantes.",
                        color=discord.Color.red(),
                    ),
                )
            except Exception:
                pass
            return

        if not results:
            try:
                await msg.edit(
                    content=None,
                    embed=discord.Embed(
                        title=f"❌ Nenhum resultado para **{product.name}**",
                        description="Tente outro termo de busca.",
                        color=discord.Color.red()
                    )
                )
            except Exception:
                try:
                    await interaction.followup.send(
                        f"❌ Nenhum resultado para **{product.name}**",
                    )
                except Exception as e:
                    logger.error(f"Failed to send 'no results' message: {e}")
            return

        try:
            embed = make_search_results_embed(results, product.name)
        except Exception as e:
            logger.error(f"Failed to create search results embed: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Erro ao formatar resultados. Tente novamente.",
                ephemeral=True
            )
            return

        try:
            await msg.edit(content=None, embed=embed)
        except Exception as e:
            logger.error(f"Failed to edit search message: {e}")
            try:
                await interaction.followup.send(embed=embed)
            except Exception as e2:
                logger.error(f"Failed to send search results as followup: {e2}")

    # ════════════════════════════════════════════════════════════════════════
    # TRACKING COMMANDS
    # ════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="monitorar", description="Começar a monitorar um produto neste canal")
    @app_commands.describe(produto="Produto para monitorar (ex: RTX 4060, iPhone 15)")
    async def cmd_monitorar(
        self,
        interaction: discord.Interaction,
        produto: str,
    ) -> None:
        """Start tracking a product in the current channel."""
        product = self.pm.parse_product_name(produto)
        
        # Check if already tracked
        if await is_product_tracked(interaction.channel_id, product.name):
            await interaction.response.send_message(
                f"⚠️ **{product.name}** já está sendo monitorado neste canal.",
                ephemeral=True,
            )
            return
        
        await add_tracked_product(interaction.channel_id, product.name, product.search_term)
        
        await interaction.response.send_message(
            f"✅ Começando a monitorar **{product.name}** neste canal!\n"
            f"🔍 Termo de busca: `{product.search_term}`\n"
            f"⏱️ Varreduras automáticas a cada {SCRAPE_INTERVAL_MINUTES} minutos.",
            ephemeral=True,
        )

    @app_commands.command(name="parar", description="Parar de monitorar um produto")
    @app_commands.describe(produto="Produto para parar de monitorar")
    async def cmd_parar(
        self,
        interaction: discord.Interaction,
        produto: str,
    ) -> None:
        """Stop tracking a product in the current channel."""
        product = self.pm.parse_product_name(produto)
        await remove_tracked_product(interaction.channel_id, product.name)
        
        await interaction.response.send_message(
            f"✅ **{product.name}** removido do monitoramento.",
            ephemeral=True,
        )

    @app_commands.command(name="lista", description="Listar produtos monitorados neste canal")
    async def cmd_lista(self, interaction: discord.Interaction) -> None:
        """List all products being tracked in the current channel."""
        tracked = await get_tracked_products(interaction.channel_id)
        
        if not tracked:
            await interaction.response.send_message(
                "📭 Nenhum produto está sendo monitorado neste canal.\n"
                f"Use `/monitorar <produto>` para começar.",
                ephemeral=True,
            )
            return
        
        products = [p["product_name"] for p in tracked]
        embed = make_tracking_list_embed(interaction.channel_id, products)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ════════════════════════════════════════════════════════════════════════
    # ALERT COMMANDS
    # ════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="alerta", description="Configura um alerta de preço pessoal")
    @app_commands.describe(
        preco="Valor em R$ para disparo (ex: 1100). Use 'cancelar' para remover.",
        produto="Produto para monitorar (ex: RTX 4060 Ti). Padrão: 5700X3D",
    )
    async def cmd_alerta(
        self,
        interaction: discord.Interaction,
        preco: str,
        produto: str = None,
    ) -> None:
        """Set or cancel a price alert."""
        user_id = str(interaction.user.id)

        if preco.lower() in ("cancelar", "cancel", "off"):
            product_name = self.pm.parse_product_name(produto).name if produto else None
            await cancel_user_alert(user_id, product_name)
            await interaction.response.send_message("✅ Alerta cancelado.", ephemeral=True)
            return

        try:
            valor = float(preco.replace("R$", "").replace(".", "").replace(",", ".").strip())
            if not (10 < valor < 50000):
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Valor inválido. Informe um número em R$ entre 10 e 50.000, ex: `/alerta 1100`",
                ephemeral=True,
            )
            return

        if produto:
            product = self.pm.parse_product_name(produto)
            product_name = product.name
            search_term = product.search_term
        else:
            product_name = PRODUCT_NAME
            search_term = "ryzen-5-5700x3d"

        await set_user_alert(user_id, valor, product_name, search_term)
        price_display = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        await interaction.response.send_message(
            f"🔔 Alerta configurado para **{product_name}** quando chegar a **{price_display}** ou menos!",
            ephemeral=True,
        )

    # ════════════════════════════════════════════════════════════════════════
    # SYSTEM COMMANDS
    # ════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="status", description="Ver status do bot e produtos monitorados")
    async def cmd_status(self, interaction: discord.Interaction) -> None:
        """Show bot status, tracked products, and store availability."""
        await interaction.response.defer(ephemeral=True)
        try:
            records = await get_all_latest()
            tracked = await get_all_tracked_products()
        except Exception as e:
            logger.error(f"Erro no /status: {e}")
            await interaction.followup.send(f"❌ Erro ao consultar DB: {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title="🤖 PreçoBot — Status",
            description=f"Monitorando preços em {len(STORE_DISPLAY_NAMES)} lojas brasileiras.",
            color=discord.Color.green(),
        )

        if records:
            by_product: dict = {}
            for r in records:
                by_product.setdefault(r.product_name, []).append(r)

            for prod_name, prod_records in by_product.items():
                store_lines = []
                for r in prod_records:
                    icon = "✅" if r.available else "❌"
                    store_display = STORE_DISPLAY_NAMES.get(r.store_id, r.store_id.title())
                    if r.price:
                        price_str = f"R$ {r.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        if r.url and r.available:
                            store_lines.append(f"{icon} [{store_display}]({r.url}) — {price_str}")
                        else:
                            store_lines.append(f"{icon} **{store_display}** — {price_str}")
                    else:
                        status_msg = "Timeout" if "timeout" in (r.stock_label or "").lower() else "Não encontrado"
                        store_lines.append(f"{icon} **{store_display}** — {status_msg}")
                embed.add_field(name=f"📦 {prod_name}", value="\n".join(store_lines), inline=False)

            last = records[0].scraped_at if records else "nunca"
            embed.add_field(name="🕐 Última varredura", value=last, inline=True)
        else:
            embed.add_field(name="⚠️ Aviso", value="Nenhum dado disponível ainda.", inline=False)

        if tracked:
            products = set(t["product_name"] for t in tracked)
            embed.add_field(
                name=f"📦 Produtos Monitorados ({len(products)})",
                value="\n".join(f"• {p}" for p in sorted(products)),
                inline=False,
            )
        else:
            embed.add_field(name="📦 Produtos Monitorados", value="Nenhum. Use `/monitorar <produto>`", inline=False)

        embed.add_field(name="⏱️ Intervalo", value=f"{SCRAPE_INTERVAL_MINUTES} minutos", inline=True)
        embed.set_footer(text="PreçoBot v2.1 · Playwright + aiosqlite")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="historico", description="Ver histórico de preços dos últimos dias")
    @app_commands.describe(dias="Número de dias a consultar (padrão: 30)")
    async def cmd_historico(
        self,
        interaction: discord.Interaction,
        dias: int = 30,
    ) -> None:
        """Show price history summary for the last N days."""
        dias = max(1, min(dias, 90))
        await interaction.response.defer(ephemeral=True)

        embeds = []
        for store_id in STORE_DISPLAY_NAMES.keys():
            records = await get_price_history(store_id, dias)
            prices = [r.price for r in records if r.price is not None]
            if not prices:
                continue
            embed = make_history_embed(
                store_id=store_id,
                min_price=min(prices),
                max_price=max(prices),
                avg_price=sum(prices) / len(prices),
                days=dias,
            )
            embeds.append(embed)

        if not embeds:
            await interaction.followup.send(
                f"📭 Sem dados históricos para os últimos {dias} dias.", ephemeral=True
            )
            return

        await interaction.followup.send(embeds=embeds[:10], ephemeral=False)

    @app_commands.command(name="ajuda", description="Lista de comandos disponíveis")
    async def cmd_ajuda(self, interaction: discord.Interaction) -> None:
        """Show help information."""
        embed = make_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MonitorCog(bot))