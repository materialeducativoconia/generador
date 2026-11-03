"""The Casting director: a picture book's guide is designed once with a model sheet, painted on the cover from it,
and lent to later tomes from the shared library at no cost."""

import json

from tests.db.test_covers import FakeImages, FakeStorage, fake_references, outlined_tome
from tests.db.test_jobs import engine, run_next  # noqa: F401  (engine is a fixture)
from tests.fakes import ScriptedLLM
from tests.test_covers import PLAN, PNG
from tests.test_themes import DESIGN

NEW = {"cast": [{"reuse": None, "based_on": None, "name": "Nilo", "role": "guide", "archetype": "niño astronauta",
                 "look": "A 6-year-old boy with brown skin and curly black hair in a white space suit with orange "
                         "stripes, round helmet under his arm.", "personality": "Curioso.",
                 "signature": "orange stripes on the suit", "palette": ["#FF7A00", "#FFFFFF", "#1E3A8A"]}],
       "reason": "nuevo"}


async def picture_book(raw_db, client, key, user, engine):
    sid = await outlined_tome(client, key, user, engine)
    await raw_db.execute("update public.series set genre = 'picture_book' where id = $1", sid)
    return sid


async def test_a_new_guide_gets_a_sheet_the_cover_follows_and_the_next_tome_borrows_it(raw_db, google_user, client,
                                                                                        key, engine):
    await raw_db.execute("delete from public.characters where name = 'Nilo'")
    images, storage = FakeImages(), FakeStorage()
    first = await picture_book(raw_db, client, key, await google_user(), engine)

    await run_next(engine, ScriptedLLM(json.dumps(DESIGN), json.dumps(NEW), json.dumps(PLAN)), covers=True,
                   images=images, storage=storage, references=fake_references)

    sheet, cover = images.calls
    assert sheet["aspect_ratio"] == "4:3" and "model sheet" in sheet["prompt"] and "Nilo" in sheet["prompt"]
    assert len(cover["references"]) == 2 and cover["references"][1] == PNG  # the sheet first, then a shelf cover
    assert "model sheets" in cover["prompt"] and "Nilo" in cover["prompt"]
    row = await raw_db.fetchrow("select id, shared, use_count, sheet_key from public.characters where name = 'Nilo'")
    assert row["shared"] and row["use_count"] == 1 and ("images", row["sheet_key"]) in storage.uploads
    cast = json.loads(await raw_db.fetchval('select "cast" from public.series where id = $1', first))
    assert cast[0]["character_id"] == str(row["id"]) and cast[0]["name"] == "Nilo"

    second = await picture_book(raw_db, client, key, await google_user(), engine)
    reuse = {"cast": [{**NEW["cast"][0], "reuse": str(row["id"])}], "reason": "encaja"}
    images.calls.clear()
    await run_next(engine, ScriptedLLM(json.dumps(DESIGN), json.dumps(reuse), json.dumps(PLAN)), covers=True,
                   images=images, storage=storage, references=fake_references)

    assert len(images.calls) == 1  # the cover only: the guide's sheet is already in the library
    assert await raw_db.fetchval("select use_count from public.characters where id = $1", row["id"]) == 2
    cast = json.loads(await raw_db.fetchval('select "cast" from public.series where id = $1', second))
    assert cast[0]["character_id"] == str(row["id"])


async def test_a_worksheet_tome_has_no_cast(raw_db, google_user, client, key, engine):
    images, storage = FakeImages(), FakeStorage()
    sid = await outlined_tome(client, key, await google_user(), engine)
    await raw_db.execute("update public.series set genre = 'worksheets' where id = $1", sid)

    await run_next(engine, ScriptedLLM(json.dumps(DESIGN), json.dumps(PLAN)), covers=True, images=images,
                   storage=storage, references=fake_references)

    assert len(images.calls) == 1
    assert await raw_db.fetchval('select "cast" from public.series where id = $1', sid) is None


MADE = {"name": "Tula", "role": "guide", "archetype": "tortuga marina exploradora",
        "look": "A small green sea turtle with a round friendly face, big dark eyes, a teal shell with yellow "
                "hexagon spots and a little red snorkel mask pushed up on her head.",
        "personality": "Tranquila y curiosa.", "signature": "a red snorkel mask", "palette": ["#2BB673", "#FFD23F", "#E63946"]}


async def test_a_creator_makes_a_private_character_in_a_house_style(raw_db, google_user, client, key, engine):
    from tests.db.test_admin import bearer

    images, storage = FakeImages(), FakeStorage()
    creator = await google_user(plan="creador", credits=50)
    made = await client.post("/api/characters", json={"description": "una tortuga marina con careta roja",
                                                      "style": "collage"}, headers=bearer(key, creator))
    assert made.status_code == 202
    char = made.json()["character"]["id"]
    await raw_db.execute("update public.generation_jobs set status = 'cancelled' where kind = 'cover' and status = 'queued'")

    await run_next(engine, ScriptedLLM(json.dumps(MADE)), images=images, storage=storage)

    row = await raw_db.fetchrow("select name, status, shared, sheet_key from public.characters where id = $1::uuid", char)
    assert row["name"] == "Tula" and row["status"] == "ready" and not row["shared"]
    assert "Cut-paper" in images.calls[0]["prompt"] and "Tula" in images.calls[0]["prompt"]
    assert await raw_db.fetchval("select style from public.character_sheets where character_id = $1::uuid", char) == "collage"
    listed = (await client.get("/api/characters", headers=bearer(key, creator))).json()["characters"]
    assert listed[0]["id"] == char and listed[0]["mine"] and listed[0]["styles"] == ["collage"]

    teacher = await google_user(plan="docente")
    denied = await client.post("/api/characters", json={"description": "un robot amable"}, headers=bearer(key, teacher))
    assert denied.status_code == 403


async def test_a_picked_guide_is_redrawn_once_in_the_tomes_house_style(raw_db, google_user, client, key, engine):
    from tests.db.test_admin import bearer
    from tests.db.test_jobs import NEW_TOME, OUTLINE

    images, storage = FakeImages(), FakeStorage()
    user = await google_user()
    guide = await raw_db.fetchval(
        """insert into public.characters (name, archetype, look, signature, sheet_key, shared)
           values ('Pepa', 'niña inventora', 'A girl with a yellow helmet.', 'yellow helmet', 'characters/pepa.jpg',
                   true) returning id""")
    storage.uploads[("images", "characters/pepa.jpg")] = (PNG, "image/jpeg")
    created = await client.post("/api/series", json={**NEW_TOME, "house_style": "gouache", "guide_id": str(guide)},
                                headers=bearer(key, user))
    sid = created.json()["series"]["id"]
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)), covers=True)
    await raw_db.execute("update public.series set genre = 'picture_book' where id = $1::uuid", sid)

    await run_next(engine, ScriptedLLM(json.dumps(DESIGN), json.dumps(PLAN)), covers=True, images=images,
                   storage=storage, references=fake_references)

    restyle, cover = images.calls  # no casting call: the user chose Pepa
    assert "same character" in restyle["prompt"] and "risograph" in restyle["prompt"]
    cast = json.loads(await raw_db.fetchval('select "cast" from public.series where id = $1::uuid', sid))
    assert cast[0]["name"] == "Pepa" and cast[0]["sheet_key"] == f"characters/{guide}-gouache.jpg"
    await raw_db.execute("delete from public.characters where id = $1", guide)


async def test_a_new_story_casts_the_character_its_request_names_and_the_library_keeps_it_nameless(
        raw_db, google_user, client, key, engine):
    await raw_db.execute("delete from public.characters where look like 'A 8-year-old girl%'")
    images, storage = FakeImages(), FakeStorage()
    sid = await picture_book(raw_db, client, key, await google_user(), engine)
    await raw_db.execute(
        """update public.series set extra_instructions = 'Karla ayuda a Lía a volver a casa',
                  "cast" = '[{"character_id": null, "name": "Lía", "look": "a girl", "sheet_key": null, "extend": true}]'::jsonb
            where id = $1""", sid)
    karla = {"cast": [{**NEW["cast"][0], "name": "Karla", "archetype": "niña exploradora",
                       "look": "A 8-year-old girl with tan skin, two black braids, a yellow raincoat and green boots."}],
             "reason": "la pide el usuario"}

    await run_next(engine, ScriptedLLM(json.dumps(DESIGN), json.dumps(karla), json.dumps(PLAN)), covers=True,
                   images=images, storage=storage, references=fake_references)

    cast = json.loads(await raw_db.fetchval('select "cast" from public.series where id = $1', sid))
    assert [c["name"] for c in cast] == ["Lía", "Karla"] and not any("extend" in c for c in cast)
    row = await raw_db.fetchrow(
        "select name, shared, topics from public.characters where look like 'A 8-year-old girl%'")
    assert row["name"] == "Niña exploradora" and row["shared"] and not any("karla" in t for t in row["topics"])


class TwoFacedOnce:
    """The Reviewer: the first sheet has a head with two faces, the second is fine."""

    def __init__(self):
        self.seen = 0

    async def review_sheet(self, image, subjects, *, kind):
        from app.vision import Review

        self.seen += 1
        return [Review(ok=self.seen > 1, defect=self.seen == 1, issues="la cabeza de perfil tiene dos caras",
                       cost_usd=0.001)]


async def test_a_sheet_with_a_two_faced_head_is_painted_again_with_the_defect_named():
    from app.casting import paint_sheet

    images = FakeImages()

    _, cost = await paint_sheet(images, TwoFacedOnce(), "Character model sheet: Pipo", [], "Pipo")

    assert len(images.calls) == 2 and "dos caras" in images.calls[1]["prompt"]
    assert round(cost, 3) == 0.081


async def test_a_starter_whose_description_changed_gets_a_new_sheet(raw_db, engine):  # noqa: F811
    from app.casting import SEED, keep_seeded

    pipo = next(c for c in SEED if c["name"] == "Pipo")
    await raw_db.execute("delete from public.characters where seed")
    images, storage = FakeImages(), FakeStorage()
    char = await raw_db.fetchval(
        """insert into public.characters (name, role, archetype, look, style, sheet_key, shared, seed, status)
           values ('Pipo', 'companion', 'perrito compañero', 'an old look', 'x', 'characters/old.jpg', true, true, 'ready')
           returning id""")
    await raw_db.execute("insert into public.character_sheets (character_id, style, sheet_key) values ($1, 'acuarela', 'k')",
                         char)

    import app.casting as casting
    casting.PAUSE_SECONDS, pause = 0, casting.PAUSE_SECONDS
    try:
        await keep_seeded(engine, images, storage)
    finally:
        casting.PAUSE_SECONDS = pause

    row = await raw_db.fetchrow("select look, sheet_key from public.characters where id = $1", char)
    assert row["look"] == pipo["look"] and row["sheet_key"] == f"characters/{char}.jpg"
    assert await raw_db.fetchval("select count(*) from public.character_sheets where character_id = $1", char) == 0
