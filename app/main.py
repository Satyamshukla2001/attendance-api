from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, cast

from fastapi import FastAPI  # type: ignore[import-not-found]
from fastapi.staticfiles import StaticFiles  # type: ignore[import-not-found]

from . import __version__
from .db import close_db, init_db
from .routers import analytics, attendance


STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: object) -> AsyncGenerator[None]:
    await init_db()
    try:
        yield
    finally:
        close_db()


app = cast(Any, FastAPI(
    title="Employee Attendance & Analytics API",
    version=__version__,
    lifespan=lifespan,
))
attendance_router = getattr(attendance, "router")
analytics_router = getattr(analytics, "router")

app.include_router(attendance_router)
app.include_router(analytics_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
