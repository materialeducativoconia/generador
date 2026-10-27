import uuid

from tests.auth_helpers import SigningKey


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
