"""FastAPI app factory.

uv run uvicorn backend.api.app:app --reload --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import dev_routes, payments_routes, routes, voice_routes
from backend.api.deps import Services
from backend.catalog.loader import load_catalog
from backend.config import Settings, get_settings
from backend.messaging import MockMessenger
from backend.store import Store

VERSION = "0.2.0"


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    """With `services` (tests), the app uses them as-is; otherwise the lifespan opens the pool."""
    settings = settings or (services.settings if services else get_settings())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if services is not None:
            app.state.services = services
            yield
            return
        with ExitStack() as stack:
            db_url = settings.supabase_db_url
            if not db_url and settings.vaani_dev_db == "ephemeral":
                # Local voice testing without Supabase: a throwaway Postgres, seeded, deleted on exit.
                from backend import devdb

                db_url = stack.enter_context(devdb.ephemeral_cluster())
                devdb.apply_all(db_url)
            if not db_url:
                raise RuntimeError("SUPABASE_DB_URL is not set (see .env.example), or set VAANI_DEV_DB=ephemeral")
            store = Store(db_url)
            await store.open()
            app.state.services = Services(settings, store, load_catalog(settings.data_dir), MockMessenger())
            try:
                yield
            finally:
                await store.close()

    app = FastAPI(title="Vaani backend", version=VERSION, lifespan=lifespan)
    if services is not None:
        app.state.services = services  # also available without running the lifespan
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.public_base_url, "http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        svc: Services = app.state.services
        try:
            db = (await svc.store.fetchrow("select 1 as ok")) is not None
        except Exception:  # noqa: BLE001 - health must answer even when the DB is down
            db = False
        return {"ok": db, "version": VERSION, "db": db}

    app.include_router(routes.router)
    app.include_router(payments_routes.router)
    app.include_router(dev_routes.router)
    app.include_router(voice_routes.router)
    return app


app = create_app()  # uvicorn backend.api.app:app (DB pool opens at startup)
