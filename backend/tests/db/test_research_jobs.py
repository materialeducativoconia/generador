"""Phase 3: the Researcher grounds the outline and sections in sources; photos come from Commons when possible."""

import json

from app.research import Document, Photo
from tests.db.test_covers import FakeStorage
from tests.db.test_illustrations import ART, FakeImages, FakeVision, empty_library, image  # noqa: F401
from tests.db.test_jobs import OUTLINE, SECTION, engine, new_tome, run_next  # noqa: F401  (fixtures)
from tests.db.test_me import bearer
from tests.fakes import ScriptedLLM
from tests.test_covers import PNG

PLAN = {"needed": True, "queries": ["Ciclo hidrológico"], "reason": "ciencias"}
FACTS = {"facts": [{"text": "El agua se evapora con el calor del Sol.", "source": 1}]}


class FakeWeb:
    def __init__(self, photo=True):
        self.searches, self.photo_queries, self.photo = [], [], photo

    async def wikipedia(self, queries, *, lang="es", **kw):
        self.searches.append((queries, lang))
        return [Document("Ciclo hidrológico", "https://es.wikipedia.org/wiki/Ciclo_hidrol%C3%B3gico", "El agua...")]

    async def commons_photo(self, query):
        self.photo_queries.append(query)
        return Photo(PNG, "image/png", "Uoaei1", "CC BY-SA 4.0", "https://c/fox") if self.photo else None


async def test_research_grounds_the_outline_and_the_sections(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await new_tome(client, key, user)
    web, architect_llm = FakeWeb(), ScriptedLLM(json.dumps(PLAN), json.dumps(FACTS), json.dumps(OUTLINE))

    await run_next(engine, architect_llm, web=web)

    assert web.searches == [(["Ciclo hidrológico"], "es")]
    assert "El agua se evapora con el calor del Sol. [1]" in architect_llm.calls[2][1]["content"]
    research = json.loads(await raw_db.fetchval("select research from public.series where id = $1", sid))
    assert research["sources"][0]["title"] == "Ciclo hidrológico" and len(research["facts"]) == 1
    versions = await raw_db.fetch("select prompt_version from public.generation_logs where series_id = $1"
                                  " order by created_at", sid)
    assert [v["prompt_version"] for v in versions] == ["research@1", "facts@1", "architect@1"]

    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))
    writer_llm = ScriptedLLM(json.dumps(SECTION))
    await run_next(engine, writer_llm)
    assert "El agua se evapora con el calor del Sol." in writer_llm.calls[0][1]["content"]
    detail = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()
    assert detail["research"] == {"needed": True, "facts": 1, "sources": research["sources"]}


async def test_topics_without_facts_skip_the_reading(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await new_tome(client, key, user)
    web = FakeWeb()

    await run_next(engine, ScriptedLLM(json.dumps({"needed": False, "reason": "colorear"}), json.dumps(OUTLINE)),
                   web=web)

    assert web.searches == []
    assert json.loads(await raw_db.fetchval("select research from public.series where id = $1", sid))["needed"] is False


async def test_photos_come_from_commons_with_credit_before_any_painting(raw_db, google_user, client, key, engine):
    from tests.db.test_illustrations import written_tome

    user = await google_user()
    sid = await written_tome(client, key, user, engine, {"schema_version": 1, "summary": "", "blocks": [
        image("p1", "un zorro rojo en la nieve", kind="photo", size="half"), image("l1", "un zorro para colorear")]})
    images, storage, web = FakeImages(), FakeStorage(), FakeWeb()
    art = {**ART, "photo_queries": {"1:p1": "red fox snow"}}

    await run_next(engine, ScriptedLLM(json.dumps(art)), images=images, vision=FakeVision(), storage=storage, web=web)

    assert web.photo_queries == ["red fox snow"] and len(images.calls) == 1  # only the colouring page is painted
    client._transport.app.state.storage = storage
    detail = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()
    photo_id = detail["lessons"][0]["content_json"]["blocks"][0]["asset_id"]
    assert detail["credits"] == {photo_id: "Foto: Uoaei1, CC BY-SA 4.0, Wikimedia Commons"}


async def test_a_photo_missing_on_commons_is_painted(raw_db, google_user, client, key, engine):
    from tests.db.test_illustrations import written_tome

    user = await google_user()
    await written_tome(client, key, user, engine, {"schema_version": 1, "summary": "", "blocks": [
        image("p1", "un zorro rojo", kind="photo", size="half")]})
    images = FakeImages()

    await run_next(engine, ScriptedLLM(json.dumps(ART)), images=images, vision=FakeVision(), storage=FakeStorage(),
                   web=FakeWeb(photo=False))

    assert len(images.calls) == 1
