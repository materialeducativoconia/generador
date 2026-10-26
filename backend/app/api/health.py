import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter()

DB_CHECK_TIMEOUT_SECONDS = 3


@router.get("/api/health")
async def health(request: Request) -> JSONResponse:
    engine = request.app.state.engine
    try:
        async with asyncio.timeout(DB_CHECK_TIMEOUT_SECONDS):
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
    except (SQLAlchemyError, OSError, TimeoutError):
        return JSONResponse({"status": "error", "db": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok", "db": "ok"})
