import httpx
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth import TokenVerifier
from app.main import create_app


async def get_health(engine) -> httpx.Response:
    # Health never touches auth; the verifier only fetches keys when a token arrives.
    verifier = TokenVerifier(jwks_url="http://127.0.0.1:1/jwks.json", issuer="unused")
    app = create_app(engine=engine, verifier=verifier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/health")


async def test_health_is_ok_when_database_responds():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    response = await get_health(engine)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "pdf": "ok"}
    await engine.dispose()


async def test_health_is_503_when_database_is_unreachable():
    # Port 1 on localhost refuses connections immediately.
    engine = create_async_engine("postgresql+asyncpg://user:pass@127.0.0.1:1/db")

    response = await get_health(engine)

    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "unreachable"}
    await engine.dispose()
