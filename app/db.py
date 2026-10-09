"""Lazy Mongo connection created inside the running event loop (lifespan)."""
from typing import Any, cast

from .config import MONGO_URI, DB_NAME

try:
    from motor.motor_asyncio import (  # pyright: ignore
        AsyncIOMotorClient as _AsyncIOMotorClient,  # pyright: ignore
    )
except ImportError:  # pragma: no cover
    # Optional dependency may be absent at type-check time.
    _AsyncIOMotorClient = None

# Motor's stubs are not always available for static analysis, so keep the
# constructor typed as Any to avoid "unknown variable type" errors.
AsyncIOMotorClient = cast(Any, _AsyncIOMotorClient)


class _State:
    client: Any = None
    database: Any = None
    supports_transactions: bool = False


_state = _State()


class _DBProxy:
    """`db.attendance` etc. resolve to the live database once init_db() ran."""
    def __getattr__(self, name: str) -> Any:
        if _state.database is None:
            raise RuntimeError(
                "Database is not initialized. Call init_db() first."
            )
        return getattr(_state.database, name)


db = _DBProxy()


def get_client():
    return _state.client


def supports_transactions() -> bool:
    return _state.supports_transactions


async def init_db():
    if AsyncIOMotorClient is None:
        raise RuntimeError(
            "Motor is not installed. Install the 'motor' package "
            "to use the database."
        )
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI is not configured.")

    mongo_client: Any = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
    _state.client = mongo_client
    _state.database = mongo_client[DB_NAME]
    hello = await mongo_client.admin.command("hello")
    # Transactions need a replica set (or mongos); standalone servers
    # don't have them.
    _state.supports_transactions = (
        "setName" in hello or hello.get("msg") == "isdbgrid"
    )
    await ensure_indexes()


def close_db():
    if _state.client:
        _state.client.close()
        _state.client = None
        _state.database = None
        _state.supports_transactions = False


async def ensure_indexes():
    # At most ONE open shift per employee, even under concurrent punch-ins.
    await db.attendance.create_index(
        [("employee_id", 1)],
        unique=True,
        partialFilterExpression={"status": "open"},
        name="one_open_shift_per_employee",
    )
    await db.attendance.create_index([("employee_id", 1), ("punch_in", -1)])
    await db.attendance.create_index([("work_date", 1)])
    await db.audit_log.create_index([("attendance_id", 1), ("at", 1)])
