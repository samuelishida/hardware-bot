"""
db/database.py — SQLite assíncrono com aiosqlite.

Tabelas:
  price_history  — um registro por varredura por loja
  user_alerts    — alertas de preço configurados por usuário no Discord
  tracked_products — produtos monitorados por canal
  scheduler_locks — prevenção de jobs concorrentes

Usa aiosqlite (async) para operações não-bloqueantes.
"""

import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "precobot.db"


async def init_db() -> None:
    """Cria as tabelas se não existirem. Chamar uma vez no startup."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS price_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id    TEXT    NOT NULL,          -- ex: "kabum"
                product_name TEXT   NOT NULL DEFAULT 'AMD Ryzen 5 5700X3D',  -- legacy default, see config.DEFAULT_PRODUCT
                search_term TEXT    NOT NULL DEFAULT 'ryzen-5-5700x3d',  -- legacy default, see config.DEFAULT_SEARCH_TERM
                price       REAL,                      -- NULL = indisponível
                available   INTEGER NOT NULL DEFAULT 0, -- 0 ou 1
                stock_label TEXT,                      -- "em estoque", "poucos", etc.
                url         TEXT,
                scraped_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_ph_store_time
                ON price_history(store_id, scraped_at DESC);
            
            CREATE INDEX IF NOT EXISTS idx_ph_product
                ON price_history(product_name, scraped_at DESC);

            CREATE TABLE IF NOT EXISTS user_alerts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_user  TEXT    NOT NULL,   -- user_id como string
                product_name  TEXT    NOT NULL DEFAULT 'AMD Ryzen 5 5700X3D',  -- legacy default, see config.DEFAULT_PRODUCT
                search_term   TEXT    NOT NULL DEFAULT 'ryzen-5-5700x3d',  -- legacy default, see config.DEFAULT_SEARCH_TERM
                target_price  REAL    NOT NULL,   -- dispara quando preço <= este valor
                active        INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );
            
            CREATE TABLE IF NOT EXISTS tracked_products (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id      TEXT    NOT NULL,
                product_name    TEXT    NOT NULL,
                search_term     TEXT    NOT NULL,
                active          INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );
            
            CREATE INDEX IF NOT EXISTS idx_tp_channel 
                ON tracked_products(channel_id, active);
            
            CREATE TABLE IF NOT EXISTS scheduler_locks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name      TEXT NOT NULL UNIQUE,
                locked_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                expires_at   TEXT NOT NULL
            );
        """)
        await db.commit()


@asynccontextmanager
async def get_db():
    """Context manager para conexão com o banco."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def acquire_lock(job_name: str, ttl_minutes: int = 10) -> bool:
    """
    Try to acquire a lock for a job.
    
    Returns True if lock acquired, False if already locked or expired.
    Lock auto-expires after ttl_minutes.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Delete expired locks
        await db.execute(
            "DELETE FROM scheduler_locks WHERE expires_at < datetime('now','localtime')"
        )
        
        # Try to insert new lock
        cursor = await db.execute(
            """INSERT OR IGNORE INTO scheduler_locks (job_name, expires_at)
               VALUES (?, datetime('now', '+' || ? || ' minutes'))""",
            (job_name, ttl_minutes)
        )
        await db.commit()
        
        return cursor.lastrowid is not None


async def release_lock(job_name: str) -> None:
    """Release a job lock."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM scheduler_locks WHERE job_name = ?", (job_name,))
        await db.commit()
