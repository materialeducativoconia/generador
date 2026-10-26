from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import health, me
from app.auth import TokenVerifier
from app.config import Settings
from app.db import make_engine
from app.errors import install_error_handlers


def create_app(engine: AsyncEngine | None = None, verifier: TokenVerifier | None = None) -> FastAPI:
    settings = Settings() if engine is None or verifier is None else None
    app = FastAPI(title="Generador API")
    app.state.engine = engine or make_engine(settings.database_url)
    app.state.verifier = verifier or TokenVerifier(jwks_url=settings.jwks_url, issuer=settings.auth_issuer)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(me.router)
    return app
