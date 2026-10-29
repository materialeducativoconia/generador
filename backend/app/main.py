import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import collections, exports, health, me, series, styles
from app.auth import TokenVerifier
from app.config import Settings
from app.db import make_engine
from app.errors import install_error_handlers
from app.storage import Storage


@asynccontextmanager
async def _embedded_worker(app: FastAPI):
    from app import worker

    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    yield
    stop.set()
    await task


def create_app(engine: AsyncEngine | None = None, verifier: TokenVerifier | None = None,
               storage: Storage | None = None) -> FastAPI:
    settings = Settings() if engine is None or verifier is None else None
    app = FastAPI(title="Generador API", lifespan=_embedded_worker if settings and settings.run_worker else None)
    app.state.engine = engine or make_engine(settings.database_url)
    app.state.verifier = verifier or TokenVerifier(jwks_url=settings.jwks_url, issuer=settings.auth_issuer)
    app.state.storage = storage or (Storage(settings.supabase_url, settings.supabase_service_role_key)
                                    if settings and settings.supabase_service_role_key else None)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(series.router)
    app.include_router(exports.router)
    app.include_router(styles.router)
    app.include_router(collections.router)
    return app
