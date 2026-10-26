"""Fixtures for tests that run against the local Supabase stack (`supabase start`)."""

import json
import os
import uuid

import asyncpg
import pytest

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
