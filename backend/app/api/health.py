import asyncio
import functools

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter()

DB_CHECK_TIMEOUT_SECONDS = 3


@functools.cache
def pdf_engine_status() -> str:
    """Whether this runtime has WeasyPrint's system libraries (Pango); the worker needs them for PDFs."""
    try:
        import weasyprint  # noqa: F401
    except ImportError:
        return "not_installed"
    except OSError:
        return "missing_system_libraries"
    return "ok"


@router.get("/api/health")
async def health(request: Request) -> JSONResponse:
    engine = request.app.state.engine
    try:
        async with asyncio.timeout(DB_CHECK_TIMEOUT_SECONDS):
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
    except (SQLAlchemyError, OSError, TimeoutError):
        return JSONResponse({"status": "error", "db": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok", "db": "ok", "pdf": pdf_engine_status()})
