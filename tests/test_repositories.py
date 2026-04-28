"""
tests/test_repositories.py — Unit tests for db/repositories/*.

Note: These tests use an in-memory SQLite database for isolation.
"""

import pytest
import pytest_asyncio
import aiosqlite
from typing import AsyncGenerator

from db.repositories.price_repo import (
    insert_price,
    get_latest_by_store,
    get_all_latest,
    get_price_history,
    get_historical_min,
    PriceRecord,
)
from db.repositories.alert_repo import (
    set_user_alert,
    get_active_alerts,
    deactivate_alert,
    cancel_user_alert,
)
from db.repositories.tracking_repo import (
    add_tracked_product,
    get_tracked_products,
    remove_tracked_product,
    get_all_tracked_products,
    is_product_tracked,
)


# Test database fixture
@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Create an in-memory test database."""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    
    # Create tables
    await db.execute("""
        CREATE TABLE price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id TEXT NOT NULL,
            product_name TEXT DEFAULT 'AMD Ryzen 5 5700X3D',
            search_term TEXT DEFAULT 'ryzen-5-5700x3d',
            price REAL,
            available INTEGER,
            stock_label TEXT,
            url TEXT,
            scraped_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    await db.execute("""
        CREATE TABLE user_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_user TEXT NOT NULL,
            product_name TEXT DEFAULT 'AMD Ryzen 5 5700X3D',
            search_term TEXT DEFAULT 'ryzen-5-5700x3d',
            target_price REAL NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    await db.execute("""
        CREATE TABLE tracked_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            search_term TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    await db.commit()
    
    # Patch get_db to use test database
    import db.database
    original_get_db = db.database.get_db
    
    async def test_get_db():
        return db
    
    db.database.get_db = test_get_db
    
    yield db
    
    # Restore original get_db
    db.database.get_db = original_get_db
    await db.close()


class TestPriceRepository:
    """Tests for price_repo.py functions."""
    
    @pytest.mark.asyncio
    async def test_insert_and_get_latest(self, test_db):
        """Test inserting and retrieving latest price."""
        await insert_price(
            store_id="kabum",
            price=1500.00,
            available=True,
            stock_label="Em estoque",
            url="https://kabum.com.br/product",
            product_name="RTX 4060",
            search_term="rtx-4060",
        )
        
        latest = await get_latest_by_store("kabum", product_name="RTX 4060")
        assert latest is not None
        assert latest.price == 1500.00
        assert latest.available is True
        assert latest.store_id == "kabum"
    
    @pytest.mark.asyncio
    async def test_get_latest_by_store_product_filter(self, test_db):
        """Test that get_latest_by_store filters by product."""
        # Insert two products for same store
        await insert_price(
            store_id="kabum",
            price=1500.00,
            available=True,
            stock_label="",
            url="",
            product_name="RTX 4060",
            search_term="rtx-4060",
        )
        await insert_price(
            store_id="kabum",
            price=2500.00,
            available=True,
            stock_label="",
            url="",
            product_name="RTX 4070",
            search_term="rtx-4070",
        )
        
        # Should only get RTX 4060 price
        latest = await get_latest_by_store("kabum", product_name="RTX 4060")
        assert latest.price == 1500.00
    
    @pytest.mark.asyncio
    async def test_get_all_latest(self, test_db):
        """Test getting latest prices for all stores."""
        await insert_price("kabum", 1500.00, True, "", "", "RTX 4060", "rtx-4060")
        await insert_price("pichau", 1600.00, True, "", "", "RTX 4060", "rtx-4060")
        
        results = await get_all_latest(product_name="RTX 4060")
        assert len(results) == 2
    
    @pytest.mark.asyncio
    async def test_get_historical_min(self, test_db):
        """Test getting historical minimum price."""
        await insert_price("kabum", 1500.00, True, "", "", "RTX 4060", "rtx-4060")
        await insert_price("kabum", 1400.00, True, "", "", "RTX 4060", "rtx-4060")
        await insert_price("kabum", 1600.00, True, "", "", "RTX 4060", "rtx-4060")
        
        min_price = await get_historical_min(days=30, product_name="RTX 4060")
        assert min_price.price == 1400.00


class TestAlertRepository:
    """Tests for alert_repo.py functions."""
    
    @pytest.mark.asyncio
    async def test_set_and_get_alert(self, test_db):
        """Test setting and retrieving a user alert."""
        await set_user_alert("123456", 1500.00, "RTX 4060", "rtx-4060")
        
        alerts = await get_active_alerts()
        assert len(alerts) == 1
        assert alerts[0]["discord_user"] == "123456"
        assert alerts[0]["target_price"] == 1500.00
    
    @pytest.mark.asyncio
    async def test_deactivate_alert(self, test_db):
        """Test deactivating a user alert."""
        await set_user_alert("123456", 1500.00, "RTX 4060", "rtx-4060")
        await deactivate_alert("123456")
        
        alerts = await get_active_alerts()
        assert len(alerts) == 0
    
    @pytest.mark.asyncio
    async def test_cancel_alert_by_product(self, test_db):
        """Test canceling alert for specific product."""
        await set_user_alert("123456", 1500.00, "RTX 4060", "rtx-4060")
        await set_user_alert("123456", 2500.00, "RTX 4070", "rtx-4070")
        
        await cancel_user_alert("123456", "RTX 4060")
        
        alerts = await get_active_alerts()
        assert len(alerts) == 1
        assert alerts[0]["product_name"] == "RTX 4070"


class TestTrackingRepository:
    """Tests for tracking_repo.py functions."""
    
    @pytest.mark.asyncio
    async def test_add_and_get_tracked_product(self, test_db):
        """Test adding and retrieving a tracked product."""
        await add_tracked_product("987654", "RTX 4060", "rtx-4060")
        
        tracked = await get_tracked_products("987654")
        assert len(tracked) == 1
        assert tracked[0]["product_name"] == "RTX 4060"
    
    @pytest.mark.asyncio
    async def test_is_product_tracked(self, test_db):
        """Test checking if product is tracked."""
        await add_tracked_product("987654", "RTX 4060", "rtx-4060")
        
        assert await is_product_tracked("987654", "RTX 4060") is True
        assert await is_product_tracked("987654", "RTX 4070") is False
    
    @pytest.mark.asyncio
    async def test_remove_tracked_product(self, test_db):
        """Test removing a tracked product."""
        await add_tracked_product("987654", "RTX 4060", "rtx-4060")
        await remove_tracked_product("987654", "RTX 4060")
        
        tracked = await get_tracked_products("987654")
        assert len(tracked) == 0
    
    @pytest.mark.asyncio
    async def test_get_all_tracked_products(self, test_db):
        """Test getting all tracked products across channels."""
        await add_tracked_product("987654", "RTX 4060", "rtx-4060")
        await add_tracked_product("111111", "RTX 4070", "rtx-4070")
        
        all_tracked = await get_all_tracked_products()
        assert len(all_tracked) == 2
