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
