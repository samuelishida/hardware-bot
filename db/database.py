"""
db/database.py — SQLite assíncrono com aiosqlite.

Tabelas:
  price_history    — um registro por varredura por loja; campos de display em data JSON
  user_alerts      — alertas de preço configurados por usuário no Discord
  tracked_products — produtos monitorados por canal
  scheduler_locks  — prevenção de jobs concorrentes
  selector_overrides — seletores CSS auto-corrigidos (self-healing, Inc 6)
  agent_runs       — 1 linha por execução do pipeline MAS (observabilidade, Inc 8)

performance notes:
  - WAL + synchronous=NORMAL: safe for single-process, ~3x faster writes
  - cache_size -2000: 2MB page cache per connection
  - mmap_size 16MB: faster reads on Linux via memory-mapped I/O
  - temp_store MEMORY: avoid temp file I/O for sorts/indexes
  - busy_timeout 5000ms: retry on lock instead of failing immediately
"""

import logging
import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "precobot.db"


async def _configure(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        PRAGMA cache_size = -2000;
        PRAGMA mmap_size = 16777216;
        PRAGMA temp_store = MEMORY;
        PRAGMA busy_timeout = 5000;
    """)


async def init_db() -> None:
    """Create tables if they don't exist and auto-migrate legacy schema."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _configure(db)
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS price_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id     TEXT    NOT NULL,
                product_name TEXT    NOT NULL DEFAULT 'AMD Ryzen 5 5700X3D',
                price        REAL,
                available    INTEGER NOT NULL DEFAULT 0,
                scraped_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                data         TEXT    NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_ph_store_time
                ON price_history(store_id, scraped_at DESC);

            CREATE INDEX IF NOT EXISTS idx_ph_product
                ON price_history(product_name, scraped_at DESC);

            CREATE TABLE IF NOT EXISTS user_alerts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_user  TEXT    NOT NULL,
                product_name  TEXT    NOT NULL DEFAULT 'AMD Ryzen 5 5700X3D',
                search_term   TEXT    NOT NULL DEFAULT 'ryzen-5-5700x3d',
                target_price  REAL    NOT NULL,
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

            CREATE TABLE IF NOT EXISTS selector_overrides (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id      TEXT    NOT NULL,
                element       TEXT    NOT NULL,            -- 'price' | 'title' | 'stock'
                selector      TEXT    NOT NULL,
                source        TEXT    NOT NULL DEFAULT 'self_healing',
                validated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                success_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(store_id, element)
            );

            CREATE INDEX IF NOT EXISTS idx_so_store_element
                ON selector_overrides(store_id, element);

            CREATE TABLE IF NOT EXISTS relevance_overrides (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id   TEXT    NOT NULL,
                term       TEXT    NOT NULL,
                source     TEXT    NOT NULL DEFAULT 'llm',
                created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                UNIQUE(store_id, term)
            );

            CREATE INDEX IF NOT EXISTS idx_ro_store
                ON relevance_overrides(store_id);

            CREATE TABLE IF NOT EXISTS agent_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      TEXT    NOT NULL,
                product     TEXT    NOT NULL,
                started_at  TEXT    NOT NULL,
                finished_at TEXT,
                status      TEXT    NOT NULL,              -- ok | partial | error
                nodes_json  TEXT,                          -- trace serializado
                error       TEXT,
                duration_ms INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_agent_runs_started
                ON agent_runs(started_at DESC);

        """)
        await db.commit()
        await _auto_migrate(db)


async def _auto_migrate(db: aiosqlite.Connection) -> None:
    """Detect legacy flat schema and migrate to JSON data column."""
    rows = await db.execute_fetchall("PRAGMA table_info(price_history)")
    col_names = {row[1] for row in rows}
    legacy = {"stock_label", "url", "search_term"}
    if legacy & col_names:
        missing = legacy - col_names
        if missing:
            # Schema híbrido/parcial: migrar agora quebraria (INSERT referencia
            # colunas que não existem) e o DROP destruiria a tabela. Pula a
            # migração em vez de corromper o histórico.
            logger.warning(
                f"Legacy price_history schema parcial ({sorted(missing)} ausentes) — "
                "migração pulada para evitar corrupção; usando schema atual."
            )
            return
        logger.warning("Legacy price_history schema detected — migrating to JSON data column")
        await _migrate_price_history(db)


async def _migrate_price_history(db: aiosqlite.Connection) -> None:
    """Migrate price_history: pack stock_label, url, search_term into JSON data column."""
    await db.execute("DROP TABLE IF EXISTS price_history_new")
    await db.execute("""
        CREATE TABLE price_history_new (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id     TEXT    NOT NULL,
            product_name TEXT    NOT NULL DEFAULT 'AMD Ryzen 5 5700X3D',
            price        REAL,
            available    INTEGER NOT NULL DEFAULT 0,
            scraped_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            data         TEXT    NOT NULL DEFAULT '{}'
        )
    """)
    await db.execute("""
        INSERT INTO price_history_new (id, store_id, product_name, price, available, scraped_at, data)
        SELECT
            id, store_id, product_name, price, available, scraped_at,
            json_object(
                'search_term', COALESCE(search_term, 'ryzen-5-5700x3d'),
                'stock_label', stock_label,
                'url',         url
            )
        FROM price_history
    """)
    await db.execute("DROP TABLE price_history")
    await db.execute("ALTER TABLE price_history_new RENAME TO price_history")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_ph_store_time ON price_history(store_id, scraped_at DESC)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_ph_product ON price_history(product_name, scraped_at DESC)")
    await db.commit()
    logger.info("Migration complete.")


@asynccontextmanager
async def get_db():
    """Async context manager for a configured DB connection."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _configure(db)
        yield db


async def get_db_stats() -> dict:
    """Return price cache statistics, agent-run count and DB file size."""
    async with get_db() as db:
        rows = await db.execute_fetchall("""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT product_name) AS products,
                MIN(scraped_at) AS oldest,
                MAX(scraped_at) AS newest
            FROM price_history
        """)
        r = rows[0]
        # agent_runs pode não existir em DBs antigos (pré-Inc 8) → degrade para 0
        try:
            run_rows = await db.execute_fetchall("SELECT COUNT(*) AS n FROM agent_runs")
            agent_runs = run_rows[0]["n"] or 0
        except aiosqlite.OperationalError:
            agent_runs = 0
    size_bytes = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    return {
        "total_rows": r["total_rows"] or 0,
        "products": r["products"] or 0,
        "oldest": r["oldest"],
        "newest": r["newest"],
        "agent_runs": agent_runs,
        "db_size_kb": size_bytes // 1024,
    }


async def purge_old_history(days: int = 60) -> int:
    """Delete price_history records older than N days. Returns rows deleted."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM price_history WHERE scraped_at < datetime('now', ?, 'localtime')",
            (f"-{days} days",),
        )
        await db.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info(f"Purged {deleted} price_history rows older than {days} days.")
        return deleted
