"""
bot/embeds.py — Discord Embed factory.

Centralizes all embed creation for price alerts, tables, and notifications.
"""

from __future__ import annotations
from datetime import datetime

import discord

from config import STORE_COLORS, STORE_DISPLAY_NAMES
from scrapers.base import ScrapeResult
from utils.formatters import format_price_brl, format_store_name


def make_price_drop_embed(
    result: ScrapeResult,
    previous_price: float,
    drop_pct: float,
    product_name: str = "Produto",
) -> discord.Embed:
    """Embed for price drop alerts — red border, drop icon."""
    store = format_store_name(result.store_id)
    embed = discord.Embed(
        title=f"🔴 ALERTA DE PREÇO · {product_name} — {store}",
        url=result.url or "",
        description=(
            f"O preço caiu **{drop_pct:.1f}%** "
            f"(**{format_price_brl(previous_price - result.price)}**) nas últimas varreduras."
        ),
        color=discord.Color.red(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="💰 Preço atual", value=f"**{format_price_brl(result.price)}**", inline=True)
    embed.add_field(name="📉 Era", value=f"~~{format_price_brl(previous_price)}~~", inline=True)
    embed.add_field(name="🏪 Loja", value=store, inline=True)
    embed.add_field(name="📦 Disponível", value="Sim ✅" if result.available else "Não ❌", inline=True)
    if result.stock_label:
        embed.add_field(name="🏷️ Estoque", value=result.stock_label, inline=True)
    embed.set_footer(text=f"PreçoBot · {store}")
    return embed


def make_restock_embed(result: ScrapeResult, product_name: str = "Produto") -> discord.Embed:
    """Embed for restock alerts — yellow border."""
    store = format_store_name(result.store_id)
    embed = discord.Embed(
        title=f"⚠️ RESTOQUE · {product_name} — {store}",
        url=result.url or "",
        description="O produto **voltou ao estoque** após estar indisponível.",
        color=discord.Color.yellow(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="💰 Preço", value=format_price_brl(result.price), inline=True)
    embed.add_field(name="🏪 Loja", value=store, inline=True)
    embed.add_field(name="🏷️ Estoque", value=result.stock_label or "Disponível", inline=True)
    embed.set_footer(text="PreçoBot · Alerta de disponibilidade")
    return embed


def make_user_alert_embed(
    result: ScrapeResult,
    target_price: float,
    product_name: str = "Produto",
) -> discord.Embed:
    """Embed sent via DM when user's target price is reached."""
    store = format_store_name(result.store_id)
    embed = discord.Embed(
        title="🔔 Seu alerta foi disparado!",
        url=result.url or "",
        description=(
            f"**{product_name}** chegou a **{format_price_brl(result.price)}** na {store}!\n"
            f"Você configurou alerta para **≤ {format_price_brl(target_price)}**."
        ),
        color=discord.Color.green(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="💰 Preço atual", value=format_price_brl(result.price), inline=True)
    embed.add_field(name="🏪 Loja", value=store, inline=True)
    embed.add_field(
        name="🔗 Link",
        value=f"[Ver produto]({result.url})" if result.url else "—",
        inline=True,
    )
    embed.set_footer(text="Este alerta foi desativado automaticamente.")
    return embed


def make_prices_table_embed(
    records: list[ScrapeResult],
    product_name: str = "Produto",
) -> discord.Embed:
    """
    Embed for price table — response to /precos.
    
    Shows prices from all stores with the lowest price highlighted.
    """
    embed = discord.Embed(
        title=f"📊 {product_name} — Preços nas lojas BR",
        color=discord.Color.blurple(),
        timestamp=datetime.now(),
    )
    
    # Find lowest price for highlighting
    available = [r for r in records if r.available and r.price is not None]
    lowest_price = min((r.price for r in available), default=None) if available else None
    
    for r in records:
        status = "✅ Em estoque" if r.available else "❌ Indisponível"
        highlight = "⭐ " if (r.price is not None and r.price == lowest_price) else ""
        embed.add_field(
            name=format_store_name(r.store_id),
            value=f"{highlight}**{format_price_brl(r.price)}** · {status}",
            inline=True,
        )
    
    embed.set_footer(text="PreçoBot · Use /alerta <valor> para ser notificado")
    return embed


def make_history_embed(
    store_id: str,
    min_price: float,
    max_price: float,
    avg_price: float,
    days: int,
    product_name: str = "Produto",
) -> discord.Embed:
    """Embed for historical price summary — response to /historico."""
    store = format_store_name(store_id)
    embed = discord.Embed(
        title=f"📈 Histórico — {product_name} · {store} · últimos {days} dias",
        color=STORE_COLORS.get(store_id, 0x5865F2),
        timestamp=datetime.now(),
    )
    embed.add_field(name="📉 Mínimo", value=format_price_brl(min_price), inline=True)
    embed.add_field(name="📈 Máximo", value=format_price_brl(max_price), inline=True)
    embed.add_field(name="⚖️ Média", value=format_price_brl(avg_price), inline=True)
    return embed


def make_search_results_embed(
    results: list[ScrapeResult],
    product_name: str,
) -> discord.Embed:
    """Embed for search results — response to /buscar."""
    embed = discord.Embed(
        title=f"🔍 {product_name}",
        description="Preços nas lojas brasileiras",
        color=discord.Color.blurple(),
        timestamp=datetime.now(),
    )
    
    for r in results:
        store = format_store_name(r.store_id)
        price = format_price_brl(r.price)
        status = "✅" if r.available else "❌"
        embed.add_field(
            name=f"{status} {store}",
            value=f"{price}\n{r.stock_label or ''}",
            inline=True,
        )
    
    embed.set_footer(text="PreçoBot v2.0 · Busca sob demanda")
    return embed


def make_tracking_list_embed(
    channel_id: str,
    products: list[str],
) -> discord.Embed:
    """Embed for tracked products list — response to /lista."""
    embed = discord.Embed(
        title="📦 Produtos Monitorados",
        description=f"Canal: <#{channel_id}>",
        color=discord.Color.green(),
    )
    embed.add_field(
        name=f"{len(products)} produto(s)",
        value="\n".join(f"• {p}" for p in products),
        inline=False,
    )
    embed.set_footer(text="Use /parar <produto> para remover")
    return embed


def make_help_embed() -> discord.Embed:
    """Embed for help command — response to /ajuda."""
    embed = discord.Embed(
        title="📖 Comandos do PreçoBot",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="/precos", value="Tabela de preços atual de todas as lojas", inline=False)
    embed.add_field(name="/buscar <produto>", value="Busca preços de qualquer produto agora", inline=False)
    embed.add_field(name="/monitorar <produto>", value="Começa a monitorar um produto neste canal", inline=False)
    embed.add_field(name="/parar <produto>", value="Para de monitorar um produto", inline=False)
    embed.add_field(name="/lista", value="Lista produtos monitorados neste canal", inline=False)
    embed.add_field(name="/historico [dias]", value="Resumo de preços dos últimos N dias (padrão: 30)", inline=False)
    embed.add_field(name="/alerta <valor>", value="Configura alerta pessoal por DM quando o preço atingir o valor", inline=False)
    embed.add_field(name="/alerta cancelar", value="Remove seu alerta ativo", inline=False)
    embed.add_field(name="/status", value="Status do bot e lojas", inline=False)
    return embed
