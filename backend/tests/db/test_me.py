import json
import uuid

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth import TokenVerifier
from app.main import create_app
from tests.auth_helpers import ISSUER, SigningKey, serve_jwks
from tests.db.conftest import LOCAL_SUPABASE_DB_URL


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


def bearer(key: SigningKey, user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {key.token(str(user_id))}"}


async def test_me_returns_profile_with_full_quota_for_a_new_teacher(google_user, client, key):
    user = await google_user()

    response = await client.get("/api/me", headers=bearer(key, user))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user)
    assert body["display_name"] == "Marta Pérez"
    assert body["avatar_url"] == "https://lh3.googleusercontent.com/a/x"
    assert body["quota"] == {"daily_lessons": 60, "used_today": 0, "remaining_today": 60}


async def test_me_counts_only_lesson_jobs_created_today(raw_db, google_user, client, key):
    user = await google_user()
    series = await raw_db.fetchval(
        """
        insert into public.series (user_id, topic, audience, language, format, lesson_count, lesson_duration_minutes, status)
        values ($1, 'Tema', '{}', 'es', 'lesson_series', 3, 45, 'generating') returning id
        """,
        user,
    )
    for kind, created_at in [
        ("lesson", "now()"),
        ("lesson_block", "now()"),
        ("outline", "now()"),  # outlines don't spend lesson quota
        ("lesson", "now() - interval '1 day'"),  # yesterday's quota is gone
    ]:
        await raw_db.execute(
            f"insert into public.generation_jobs (user_id, series_id, kind, status, payload, created_at)"
            f" values ($1, $2, '{kind}', 'succeeded', '{{}}', {created_at})",
            user,
            series,
        )

    response = await client.get("/api/me", headers=bearer(key, user))

    assert response.json()["quota"] == {"daily_lessons": 60, "used_today": 2, "remaining_today": 58}


async def test_me_without_token_is_401(client):
    response = await client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_me_with_forged_token_is_401(google_user, client):
    user = await google_user()

    response = await client.get("/api/me", headers=bearer(SigningKey(), user))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_me_for_a_deactivated_account_is_403(raw_db, google_user, client, key):
    user = await google_user()
    await raw_db.execute("update public.profiles set is_active = false where id = $1", user)

    response = await client.get("/api/me", headers=bearer(key, user))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
