import json
import uuid

from tests.db.test_me import bearer

NEW_TOME = {"request": "Método de piano para principiantes", "audience": "Adultos sin experiencia", "section_count": 3}


async def create_tome(client, key, user, **overrides):
    response = await client.post("/api/series", json={**NEW_TOME, **overrides}, headers=bearer(key, user))
    assert response.status_code == 202, response.text
    return response.json()


async def outline_ready(raw_db, series_id, titles=("Postura", "Do central", "Primera melodía")):
    """Puts a series where the Architect leaves it: lessons from the outline and status outline_ready."""
    for i, title in enumerate(titles, 1):
        await raw_db.execute(
            "insert into public.lessons (series_id, position, title, objectives, key_points, status)"
            " values ($1, $2, $3, '[\"Tocar\"]', '[\"Do\"]', 'pending')",
            series_id, i, title,
        )
    await raw_db.execute(
        "update public.series set status = 'outline_ready', title = 'Piano desde cero', genre = 'tutorial',"
        " lesson_count = $2 where id = $1",
        series_id, len(titles),
    )


async def test_create_tome_queues_the_architect(raw_db, google_user, client, key):
    user = await google_user()

    body = await create_tome(client, key, user)

    assert body["series"]["status"] == "outlining"
    assert body["job"]["kind"] == "outline"
    job = await raw_db.fetchrow("select status, payload from public.generation_jobs where id = $1",
                                uuid.UUID(body["job"]["id"]))
    assert job["status"] == "queued"
    assert json.loads(job["payload"])["brief"]["request"] == NEW_TOME["request"]


async def test_create_tome_is_idempotent(raw_db, google_user, client, key):
    user = await google_user()
    headers = {**bearer(key, user), "Idempotency-Key": "abc-123"}

    first = await client.post("/api/series", json=NEW_TOME, headers=headers)
    second = await client.post("/api/series", json=NEW_TOME, headers=headers)

    assert first.json()["series"]["id"] == second.json()["series"]["id"]
    assert await raw_db.fetchval("select count(*) from public.series where user_id = $1", user) == 1


async def test_create_tome_validates_input(google_user, client, key):
    user = await google_user()

    response = await client.post("/api/series", json={"request": "", "audience": "x"}, headers=bearer(key, user))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_list_and_get_only_show_own_tomes(google_user, client, key):
    marta, pedro = await google_user(), await google_user()
    mine = await create_tome(client, key, marta)

    listed = (await client.get("/api/series", headers=bearer(key, marta))).json()
    other = await client.get(f"/api/series/{mine['series']['id']}", headers=bearer(key, pedro))

    assert [s["id"] for s in listed["series"]] == [mine["series"]["id"]]
    assert other.status_code == 404


async def test_edit_outline_reorders_adds_and_removes_sections(raw_db, google_user, client, key):
    user = await google_user()
    sid = (await create_tome(client, key, user))["series"]["id"]
    await outline_ready(raw_db, uuid.UUID(sid))
    lessons = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()["lessons"]

    response = await client.patch(
        f"/api/series/{sid}/outline",
        json={"version": 1, "title": "Piano fácil", "lessons": [
            {"id": lessons[2]["id"], "title": "Melodía", "objectives": [], "key_points": []},
            {"id": lessons[0]["id"], "title": "Postura", "objectives": ["Sentarse"], "key_points": []},
            {"title": "Nueva", "objectives": [], "key_points": []},
        ]},
        headers=bearer(key, user),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Piano fácil" and body["version"] == 2
    assert [lesson["title"] for lesson in body["lessons"]] == ["Melodía", "Postura", "Nueva"]


async def test_edit_outline_with_stale_version_conflicts(raw_db, google_user, client, key):
    user = await google_user()
    sid = (await create_tome(client, key, user))["series"]["id"]
    await outline_ready(raw_db, uuid.UUID(sid))

    response = await client.patch(f"/api/series/{sid}/outline", json={"version": 9, "lessons": []},
                                  headers=bearer(key, user))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_conflict"


async def test_approve_outline_queues_one_job_per_section(raw_db, google_user, client, key):
    user = await google_user()
    sid = (await create_tome(client, key, user))["series"]["id"]
    await outline_ready(raw_db, uuid.UUID(sid))

    response = await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))

    assert response.status_code == 202
    assert len(response.json()["jobs"]) == 3
    progress = (await client.get(f"/api/series/{sid}/progress", headers=bearer(key, user))).json()
    assert progress["status"] == "generating"
    assert progress["counts"]["queued"] == 3


async def test_approve_while_architect_still_works_is_invalid_state(google_user, client, key):
    user = await google_user()
    sid = (await create_tome(client, key, user))["series"]["id"]

    response = await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


async def test_approve_beyond_daily_quota_is_429(raw_db, google_user, client, key):
    user = await google_user()
    await raw_db.execute("update public.profiles set daily_lesson_quota = 2 where id = $1", user)
    sid = (await create_tome(client, key, user))["series"]["id"]
    await outline_ready(raw_db, uuid.UUID(sid))

    response = await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "quota_exceeded"
