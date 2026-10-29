"""Collections group a user's tomes by level; deleting a tome removes it and its files."""

from tests.db.test_me import bearer
from tests.db.test_series_api import create_tome


async def test_a_collection_orders_its_tomes_by_level(raw_db, google_user, client, key):
    user = await google_user()
    first = (await create_tome(client, key, user))["series"]["id"]
    second = (await create_tome(client, key, user))["series"]["id"]
    h = bearer(key, user)

    made = await client.post("/api/collections", json={"name": "Multiplicación", "series_ids": [first, second]},
                             headers=h)
    cid = made.json()["collection"]["id"]
    lower = (await create_tome(client, key, user, collection_id=cid, place="start"))["series"]["id"]
    higher = (await create_tome(client, key, user, collection_id=cid))["series"]["id"]

    listed = (await client.get("/api/collections", headers=h)).json()["collections"]
    assert listed[0]["name"] == "Multiplicación" and listed[0]["series_ids"] == [lower, first, second, higher]
    tomes = {s["id"]: s for s in (await client.get("/api/series", headers=h)).json()["series"]}
    assert tomes[first]["collection_id"] == cid

    await client.put(f"/api/series/{first}/collection", json={"collection_id": None}, headers=h)
    await client.patch(f"/api/collections/{cid}", json={"name": "Multiplicar"}, headers=h)
    listed = (await client.get("/api/collections", headers=h)).json()["collections"]
    assert listed[0]["name"] == "Multiplicar" and first not in listed[0]["series_ids"]

    assert (await client.delete(f"/api/collections/{cid}", headers=h)).status_code == 204
    assert (await client.get("/api/collections", headers=h)).json()["collections"] == []
    assert await raw_db.fetchval("select count(*) from public.series where user_id = $1", user) == 4


async def test_deleting_a_tome_takes_its_sections_and_jobs(raw_db, google_user, client, key):
    user = await google_user()
    sid = (await create_tome(client, key, user))["series"]["id"]

    assert (await client.delete(f"/api/series/{sid}", headers=bearer(key, user))).status_code == 204

    assert await raw_db.fetchval("select count(*) from public.series where id = $1", sid) == 0
    assert await raw_db.fetchval("select count(*) from public.generation_jobs where series_id = $1", sid) == 0
    assert (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).status_code == 404


async def test_nobody_touches_another_users_tomes_or_collections(raw_db, google_user, client, key):
    owner, other = await google_user(), await google_user()
    sid = (await create_tome(client, key, owner))["series"]["id"]
    cid = (await client.post("/api/collections", json={"name": "Mía"}, headers=bearer(key, owner))).json()[
        "collection"]["id"]
    h = bearer(key, other)

    assert (await client.delete(f"/api/series/{sid}", headers=h)).status_code == 404
    assert (await client.delete(f"/api/collections/{cid}", headers=h)).status_code == 404
    assert (await client.post("/api/collections", json={"name": "x", "series_ids": [sid]}, headers=h)).status_code == 404
    assert (await create_tome_status(client, key, other, cid)) == 404


async def create_tome_status(client, key, user, cid):
    response = await client.post("/api/series", json={"request": "Piano", "audience": "Adultos", "collection_id": cid,
                                                        "section_count": 1, "page_count": 3},
                                 headers=bearer(key, user))
    return response.status_code
