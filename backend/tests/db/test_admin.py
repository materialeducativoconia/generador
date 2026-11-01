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
    assert body["previews"]["total"] >= 0 and body["users"]["new"] >= 2 and body["users"]["paying"] >= 2
    docente = next(p for p in body["revenue"]["by_plan"] if p["plan"] == "docente")
    assert docente["count"] >= 1 and docente["mrr_usd"] == 9 * docente["count"]
    assert len(body["daily"]) == 7
    assert any(u["key"] == "aula" for u in body["uses"])
    assert any(s["key"] == "Matemáticas" for s in body["subjects"])


async def test_admins_give_and_take_back_a_plan_by_hand(raw_db, google_user, client, key):
    admin = await google_user(email="jefa@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    teacher = await google_user(email="maestra@escuela.test", plan=None)
    h = bearer(key, admin)

    found = (await client.get("/api/admin/users", params={"q": "maestra"}, headers=h)).json()["users"]
    assert [u["email"] for u in found] == ["maestra@escuela.test"] and found[0]["plan"] == "prueba"

    given = await client.post(f"/api/admin/users/{teacher}/plan", json={"plan": "creador", "months": 2}, headers=h)
    assert given.status_code == 200 and given.json()["plan"] == "creador" and given.json()["credits"] == 1000
    assert (await client.get("/api/me", headers=bearer(key, teacher))).json()["plan"]["key"] == "creador"

    more = await client.post(f"/api/admin/users/{teacher}/credits", json={"amount": 50, "reason": "Bienvenida"}, headers=h)
    assert more.json()["credits"] == 1050
    back = await client.post(f"/api/admin/users/{teacher}/plan", json={"plan": None}, headers=h)
    assert back.json()["plan"] == "prueba" and back.json()["credits"] == 50  # the plan's credits go with it

    detail = (await client.get(f"/api/admin/users/{teacher}", headers=h)).json()
    assert {e["reason"] for e in detail["ledger"]} >= {"Plan Creador asignado por el equipo", "Bienvenida"}


async def test_staff_look_but_only_admins_change_things(raw_db, google_user, client, key):
    staff = await google_user(email="apoyo@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'staff' where id = $1", staff)
    other = await google_user(plan=None)
    h = bearer(key, staff)

    assert (await client.get("/api/admin/users", headers=h)).status_code == 200
    assert (await client.post(f"/api/admin/users/{other}/plan", json={"plan": "docente"}, headers=h)).status_code == 403
    assert (await client.post(f"/api/admin/users/{other}/role", json={"role": "admin"}, headers=h)).status_code == 403
    assert (await client.get("/api/admin/users", headers=bearer(key, other))).status_code == 403


async def test_a_plan_given_by_hand_ends_on_its_date(raw_db, google_user, client, key):
    admin = await google_user()
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    teacher = await google_user(plan=None)
    await client.post(f"/api/admin/users/{teacher}/plan", json={"plan": "docente"}, headers=bearer(key, admin))
    await raw_db.execute("update public.subscriptions set current_period_end = now() - interval '1 day'"
                         " where org_id = (select org_id from public.memberships where user_id = $1)", teacher)

    assert (await client.get("/api/me", headers=bearer(key, teacher))).json()["plan"]["key"] == "prueba"
