from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import health
from app.config import Settings
from app.db import make_engine


def create_app(engine: AsyncEngine | None = None) -> FastAPI:
    app = FastAPI(title="Generador API")
    app.state.engine = engine or make_engine(Settings().database_url)
    app.include_router(health.router)
    return app
