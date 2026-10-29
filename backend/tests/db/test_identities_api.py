"""Mis identidades: three candidates from the identity job, one kept, applied to a whole collection."""

import json

from tests.db.test_jobs import engine, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.db.test_series_api import create_tome
from tests.fakes import ScriptedLLM

DIRECTIONS = {"directions": [
    {"name": "Semillita", "tagline": "Aprender jugando", "personality": ["cálida", "alegre", "clara"],
     "voice": "Le habla de tú al niño, con frases cortas y ánimo.", "mascot": {"name": "Luna", "look": "a small owl"},
     "mark": "leaf", "visual_idea": "acuarela suave, verdes"},
    {"name": "Taller Brújula", "tagline": "Ideas que orientan", "personality": ["curiosa", "precisa"],
     "voice": "Usted, sobria.", "mascot": None, "mark": "shield", "visual_idea": "grabado, azul tinta"},
    {"name": "Pizarra Viva", "tagline": "Clase a clase", "personality": ["enérgica"], "voice": "Tú, con humor.",
     "mascot": None, "mark": "badge", "visual_idea": "risografía coral"},
]}
LOOK = {"theme": "juego", "palette": ["#FFFDF7", "#1C1917", "#2F855A"], "ornament": "hojas", "illustration": "acuarela",
        "cover_layout": "plate", "head_font": "Fredoka", "frame": "none", "rationale": "x"}
LOOKS = {"looks": [LOOK, LOOK, {**LOOK, "theme": "editorial", "illustration": "grabado"}]}


async def proposed(client, key, user, engine):
    h = bearer(key, user)
    made = (await client.post("/api/identities", json={"about": "Cuadernillos de matemáticas para primaria",
                                                       "personality": "cálida"}, headers=h)).json()
    llm = ScriptedLLM(json.dumps(DIRECTIONS), json.dumps(LOOKS))
    await run_next(engine, llm)
    return made["identity"]["id"], llm


async def test_the_identity_job_proposes_three_distinct_lines(raw_db, google_user, client, key, engine):
    user = await google_user()
    iid, llm = await proposed(client, key, user, engine)

    listed = (await client.get("/api/identities", headers=bearer(key, user))).json()["identities"]
    assert listed[0]["status"] == "choosing" and len(listed[0]["candidates"]) == 3
    cands = listed[0]["candidates"]
    keys = {(c["theme"], c["illustration"], c["cover_layout"], c["head_font"]) for c in cands}
    assert len(keys) == 3  # the guard split the two identical looks
    assert cands[0]["brand"]["name"] == "Semillita" and cands[0]["brand"]["initials"] == "S"
    assert "<svg" in cands[0]["mark_svg"]
    assert "Cuadernillos de matemáticas" in llm.calls[0][1]["content"]
    assert await raw_db.fetchval("select count(*) from public.generation_logs where job_id in "
                                 "(select id from public.generation_jobs where user_id = $1)", user) == 2


async def test_a_collection_follows_its_identity(raw_db, google_user, client, key, engine):
    user = await google_user()
    h = bearer(key, user)
    iid, _ = await proposed(client, key, user, engine)
    await client.post(f"/api/identities/{iid}/choose", json={"index": 0}, headers=h)
    old = (await create_tome(client, key, user))["series"]["id"]
    cid = (await client.post("/api/collections", json={"name": "Multiplicación", "series_ids": [old]},
                             headers=h)).json()["collection"]["id"]

    assert (await client.put(f"/api/collections/{cid}/identity", json={"identity_id": iid},
                             headers=h)).status_code == 200
    new = (await create_tome(client, key, user, collection_id=cid))["series"]["id"]
    loose = (await create_tome(client, key, user))["series"]["id"]
    await client.put(f"/api/series/{loose}/collection", json={"collection_id": cid}, headers=h)

    for sid in (old, new, loose):
        row = await raw_db.fetchrow("select design, identity_id from public.series where id = $1", sid)
        assert str(row["identity_id"]) == iid and json.loads(row["design"])["brand"]["name"] == "Semillita"

    await client.patch(f"/api/identities/{iid}", json={"name": "Semillita Ediciones"}, headers=h)
    design = json.loads(await raw_db.fetchval("select design from public.series where id = $1", new))
    assert design["brand"]["name"] == "Semillita Ediciones"
    listed = (await client.get("/api/collections", headers=h)).json()["collections"]
    assert listed[0]["identity_id"] == iid


async def test_nobody_uses_another_users_identity(raw_db, google_user, client, key, engine):
    owner, other = await google_user(), await google_user()
    iid, _ = await proposed(client, key, owner, engine)
    await client.post(f"/api/identities/{iid}/choose", json={"index": 1}, headers=bearer(key, owner))
    h = bearer(key, other)
    cid = (await client.post("/api/collections", json={"name": "Mía"}, headers=h)).json()["collection"]["id"]

    assert (await client.get("/api/identities", headers=h)).json()["identities"] == []
    assert (await client.put(f"/api/collections/{cid}/identity", json={"identity_id": iid},
                             headers=h)).status_code == 404
    assert (await client.delete(f"/api/identities/{iid}", headers=h)).status_code == 404
    sid = (await create_tome(client, key, other, identity_id=iid))["series"]["id"]
    assert await raw_db.fetchval("select design from public.series where id = $1", sid) is None
