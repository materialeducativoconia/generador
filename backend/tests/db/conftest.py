"""Fixtures for tests that run against the local Supabase stack (`supabase start`)."""

import json
import os
import uuid

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth import TokenVerifier
from app.main import create_app
from tests.auth_helpers import ISSUER, SigningKey, serve_jwks

LOCAL_SUPABASE_DB_URL = "postgresql://postgres:postgres@127.0.0.1:55322/postgres"


@pytest.fixture
async def db():
    url = os.environ.get("TEST_SUPABASE_DB_URL", LOCAL_SUPABASE_DB_URL)
    try:
        conn = await asyncpg.connect(url, timeout=3)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"local Supabase not reachable ({exc}); run `supabase start`")
    tx = conn.transaction()
    await tx.start()
    try:
        yield conn
    finally:
        await tx.rollback()
        await conn.close()


async def create_google_user(conn, email: str, full_name: str = "Marta Docente", avatar_url: str | None = None) -> uuid.UUID:
    """Inserts an auth.users row shaped like the one Supabase Auth creates on a first Google login."""
    meta = {"full_name": full_name, "email": email}
    if avatar_url:
        meta["avatar_url"] = avatar_url
    return await conn.fetchval(
        """
        insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data, raw_app_meta_data, created_at, updated_at)
        values (gen_random_uuid(), '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
                $1, $2::jsonb, '{"provider": "google", "providers": ["google"]}'::jsonb, now(), now())
        returning id
        """,
        email,
        json.dumps(meta),
    )


async def act_as(conn, role: str, user_id: uuid.UUID | None = None) -> None:
    """Switches the session to how PostgREST/Realtime see a request: an `anon` or `authenticated` role plus JWT claims."""
    claims = {"role": role}
    if user_id:
        claims["sub"] = str(user_id)
    await conn.execute("select set_config('request.jwt.claims', $1, true)", json.dumps(claims))
    await conn.execute(f"set local role {role}")


async def create_series(conn, user_id: uuid.UUID, lesson_count: int = 10) -> uuid.UUID:
    return await conn.fetchval(
        """
        insert into public.series (user_id, topic, audience, language, format, lesson_count, lesson_duration_minutes, status)
        values ($1, 'El ciclo del agua', '{"stage": "secundaria", "grade": "2º"}', 'es', 'lesson_series', $2, 45, 'outlining')
        returning id
        """,
        user_id,
        lesson_count,
    )


async def create_lesson(conn, series_id: uuid.UUID, position: int) -> uuid.UUID:
    return await conn.fetchval(
        """
        insert into public.lessons (series_id, position, title, objectives, key_points, status)
        values ($1, $2, $3, '["Objetivo"]', '["concepto"]', 'pending')
        returning id
        """,
        series_id,
        position,
        f"Lección {position}",
    )


async def create_job(conn, user_id: uuid.UUID, series_id: uuid.UUID, kind: str = "outline") -> uuid.UUID:
    return await conn.fetchval(
        """
        insert into public.generation_jobs (user_id, series_id, kind, status, payload)
        values ($1, $2, $3, 'queued', '{}')
        returning id
        """,
        user_id,
        series_id,
        kind,
    )


@pytest.fixture
async def raw_db():
    """Autocommit connection: the API under test uses its own pool, so it only sees committed rows."""
    try:
        conn = await asyncpg.connect(LOCAL_SUPABASE_DB_URL, timeout=3)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"local Supabase not reachable ({exc}); run `supabase start`")
    yield conn
    await conn.close()


@pytest.fixture
async def google_user(raw_db):
    """Creates committed users like a first Google login does, and deletes them (cascading) afterwards."""
    created: list[uuid.UUID] = []

    async def create(email: str | None = None, full_name: str = "Marta Pérez") -> uuid.UUID:
        user_id = await raw_db.fetchval(
            """
            insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data, raw_app_meta_data, created_at, updated_at)
            values (gen_random_uuid(), '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
                    $1, $2::jsonb, '{"provider": "google"}'::jsonb, now(), now())
            returning id
            """,
            email or f"docente-{uuid.uuid4().hex[:8]}@gmail.com",
            json.dumps({"full_name": full_name, "avatar_url": "https://lh3.googleusercontent.com/a/x"}),
        )
        created.append(user_id)
        return user_id

    yield create
    await raw_db.execute("delete from auth.users where id = any($1::uuid[])", created)


@pytest.fixture
def key():
    return SigningKey()


@pytest.fixture
async def client(key):
    engine = create_async_engine(LOCAL_SUPABASE_DB_URL.replace("postgresql://", "postgresql+asyncpg://"))
    with serve_jwks(key) as jwks_url:
        app = create_app(engine=engine, verifier=TokenVerifier(jwks_url=jwks_url, issuer=ISSUER))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    await engine.dispose()
