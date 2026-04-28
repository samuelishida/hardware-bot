"""
main.py — entry point do PreçoBot.

Responsabilidades:
  - Inicializa o banco de dados
  - Cria o bot Discord com intents corretos
  - Carrega o cog de comandos
  - Inicia o APScheduler com o job de varredura
  - Sincroniza slash commands no startup

Copilot: não adicione lógica de negócio aqui. Este arquivo só orquestra.
"""

import asyncio
import logging
import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    DISCORD_TOKEN,
    DISCORD_GUILD_ID,
    SCRAPE_INTERVAL_MINUTES,
)
from db.database import init_db
from scheduler.jobs import run_scrape_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("precobot")


class PrecoBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False  # não precisa ler mensagens
        super().__init__(command_prefix="!", intents=intents)
        self.scheduler = AsyncIOScheduler()

    async def setup_hook(self) -> None:
        """Chamado antes do bot conectar ao Discord."""
        # Banco
        await init_db()
        logger.info("Banco de dados inicializado.")

        # Cogs (slash commands)
        await self.load_extension("bot.cog_monitor")
        logger.info("Cog de monitoramento carregado.")

        # Sincroniza slash commands no servidor (mais rápido que global)
        guild = discord.Object(id=DISCORD_GUILD_ID)
        try:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Slash commands sincronizados no servidor configurado.")
        except discord.Forbidden:
            logger.warning(
                "Sem acesso ao DISCORD_GUILD_ID configurado; sincronizando comandos globalmente."
            )
            await self.tree.sync()
            logger.info("Slash commands sincronizados globalmente.")

        self.scheduler.add_job(
            run_scrape_job,
            "interval",
            minutes=SCRAPE_INTERVAL_MINUTES,
            args=[self],
            id="price_scrape",
        )
        self.scheduler.start()
        logger.info(f"Scheduler iniciado — varredura a cada {SCRAPE_INTERVAL_MINUTES} minutos.")

    async def on_ready(self) -> None:
        logger.info(f"Conectado como {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="preços 🔍",
            )
        )


async def main() -> None:
    bot = PrecoBot()
    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
