"""
MongoDB connection via Motor (async driver).
Call connect_db() on startup and close_db() on shutdown.
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_db() -> AsyncIOMotorDatabase:
    """Return the active database instance. Raises if not connected."""
    if _db is None:
        raise RuntimeError("Database not connected. Call connect_db() first.")
    return _db


async def connect_db() -> None:
    global _client, _db
    url  = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    name = os.getenv("MONGODB_DB_NAME", "lifelens")

    _client = AsyncIOMotorClient(url)
    _db     = _client[name]

    # Ping to verify connection
    await _client.admin.command("ping")
    print(f"✅ Connected to MongoDB — database: '{name}'")

    # Ensure indexes
    await _db["users"].create_index("username", unique=True)
    await _db["users"].create_index("email",    unique=True)
    await _db["videos"].create_index("user_id")
    print("✅ MongoDB indexes ready")


async def close_db() -> None:
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db     = None
        print("🔌 MongoDB connection closed")
