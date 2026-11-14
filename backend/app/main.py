import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import (adopters, admin, billing, books, characters, collections, exports, health, identities, library, marketing,
                     me, orders, pages, series, style_lab, styles, versions)
from app.auth import TokenVerifier
from app.config import Settings
from app.db import make_engine
from app.errors import install_error_handlers
from app.images import OpenRouterImages
from app.voice import OpenRouterVoice
from app.llm import DeepSeek
from app.storage import Storage
from app.stripe_gateway import StripeGateway


@asynccontextmanager
async def _embedded_worker(app: FastAPI):
    from app import worker

    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    yield
    stop.set()
    await task


def create_app(engine: AsyncEngine | None = None, verifier: TokenVerifier | None = None,
               storage: Storage | None = None, stripe=None, llm=None) -> FastAPI:
    settings = Settings() if engine is None or verifier is None else None
    app = FastAPI(title="Generador API", lifespan=_embedded_worker if settings and settings.run_worker else None)
    app.state.engine = engine or make_engine(settings.database_url)
    app.state.verifier = verifier or TokenVerifier(jwks_url=settings.jwks_url, issuer=settings.auth_issuer)
    app.state.storage = storage or (Storage(settings.supabase_url, settings.supabase_service_role_key)
                                    if settings and settings.supabase_service_role_key else None)
    app.state.stripe = stripe or (StripeGateway(settings.stripe_secret_key, settings.stripe_webhook_secret,
                                                settings.app_url)
                                  if settings and settings.stripe_secret_key else None)
    app.state.images = (OpenRouterImages(settings.openrouter_api_key, settings.openrouter_image_model)
                        if settings and settings.openrouter_api_key else None)
    app.state.voice = (OpenRouterVoice(settings.openrouter_api_key, settings.openrouter_tts_model,
                                       settings.openrouter_tts_voice)
                       if settings and settings.openrouter_api_key else None)
    # The API's own DeepSeek, for the admin's short asks (a video script); the worker keeps its own for the tomes.
    app.state.llm = llm or (DeepSeek(settings.deepseek_api_key, settings.deepseek_model, settings.deepseek_rpm,
                                      settings.deepseek_max_inflight) if settings and settings.deepseek_api_key else None)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(series.router)
    app.include_router(exports.router)
    app.include_router(styles.router)
    app.include_router(collections.router)
    app.include_router(identities.router)
    app.include_router(billing.router)
    app.include_router(admin.router)
    app.include_router(characters.router)
    app.include_router(style_lab.router)
    app.include_router(library.router)
    app.include_router(books.router)
    app.include_router(marketing.router)
    app.include_router(versions.router)
    app.include_router(pages.router)
    app.include_router(adopters.router)
    app.include_router(orders.router)
    return app
