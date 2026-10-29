import json
import uuid

from tests.auth_helpers import SigningKey


def bearer(key: SigningKey, user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {key.token(str(user_id))}"}


async def test_analytics_is_for_staff_only(google_user, client, key):
    user = await google_user()
    response = await client.get("/api/admin/analytics", headers=bearer(key, user))
    assert response.status_code == 403


async def test_analytics_counts_users_revenue_and_onboarding(raw_db, google_user, client, key):
    admin = await google_user(email="admin-analytics@example.com")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    teacher = await google_user(email="docente-analytics@example.com", plan="docente", credits=150)
    await raw_db.execute(
        "update public.profiles set onboarded_at = now(), onboarding = $2::jsonb where id = $1",
        teacher, json.dumps({"use": "aula", "levels": [], "subjects": ["Matemáticas"]}))

    response = await client.get("/api/admin/analytics?days=7", headers=bearer(key, admin))

    assert response.status_code == 200
    body = response.json()
    assert body["users"]["new"] >= 2 and body["users"]["paying"] >= 2
    docente = next(p for p in body["revenue"]["by_plan"] if p["plan"] == "docente")
    assert docente["count"] >= 1 and docente["mrr_usd"] == 9 * docente["count"]
    assert len(body["daily"]) == 7
    assert any(u["key"] == "aula" for u in body["uses"])
    assert any(s["key"] == "Matemáticas" for s in body["subjects"])
