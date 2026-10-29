"""Material by page count, and the proposed look previewed (and swappable) before anything is written."""

import json

from app.agents import spread_pages
from app.content import OutlineSection
from tests.db.test_covers import FakeImages, FakeStorage, fake_references
from tests.db.test_jobs import OUTLINE, engine, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.db.test_series_api import NEW_TOME
from tests.db.test_styles_api import LibraryStorage, uploaded_style
from tests.fakes import ScriptedLLM
from tests.test_covers import PLAN
from tests.test_themes import DESIGN


def test_pages_are_spread_to_the_target_keeping_the_architects_proportions():
    sections = [OutlineSection(title=t, pages=p) for t, p in (("a", 2), ("b", 6), ("c", None))]

    spread_pages(sections, 25)

    assert sum(s.pages for s in sections) == 25 and sections[1].pages > sections[0].pages >= sections[2].pages


async def test_a_tome_ordered_by_pages_plans_its_sections_and_design_together(raw_db, google_user, client, key,
                                                                               engine):
    user = await google_user()
    created = (await client.post("/api/series", json={**NEW_TOME, "section_count": 3, "page_count": 20},
                                 headers=bearer(key, user))).json()
    sid = created["series"]["id"]
    outline = {**OUTLINE, "sections": [{**s, "pages": p} for s, p in zip(OUTLINE["sections"], (2, 4, 4))]}
    llm = ScriptedLLM(json.dumps(outline), json.dumps(DESIGN))

    await run_next(engine, llm)

    assert "exactamente 20 páginas de contenido" in llm.calls[0][-1]["content"]
    pages = [r["pages"] for r in await raw_db.fetch(
        "select pages from public.lessons where series_id = $1 order by position", sid)]
    assert sum(pages) == 20 and pages[0] < pages[1]
    detail = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()
    assert detail["design"]["palette"] == DESIGN["palette"] and detail["lessons"][1]["pages"] == pages[1]
    preview = (await client.get(f"/api/series/{sid}/preview", headers=bearer(key, user))).json()
    assert preview["design"]["theme"] == DESIGN["theme"] and preview["blocks"]

    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))
    writer = ScriptedLLM(json.dumps({"schema_version": 1, "blocks": [{"id": "b", "type": "paragraph", "text": "x"}]}))
    await run_next(engine, writer)
    assert f"unas {pages[0]} páginas" in writer.calls[0][-1]["content"]


async def test_the_cover_job_reuses_the_design_chosen_with_the_outline(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = (await client.post("/api/series", json=NEW_TOME, headers=bearer(key, user))).json()["series"]["id"]
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE), json.dumps(DESIGN)), covers=True)
    llm = ScriptedLLM(json.dumps(PLAN))

    await run_next(engine, llm, covers=True, images=FakeImages(), storage=FakeStorage(), references=fake_references)

    assert len(llm.calls) == 1  # only the cover director
    assert json.loads(await raw_db.fetchval("select cover from public.series where id = $1", sid))["palette"] \
        == DESIGN["palette"]


async def test_the_user_swaps_the_look_before_writing(raw_db, google_user, client, key, engine):
    user = await google_user()
    _, style = await uploaded_style(client, key, user, engine, LibraryStorage())
    sid = (await client.post("/api/series", json=NEW_TOME, headers=bearer(key, user))).json()["series"]["id"]
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE), json.dumps(DESIGN)))

    themed = (await client.patch(f"/api/series/{sid}/design", json={"theme": "ciencia"},
                                 headers=bearer(key, user))).json()
    styled = (await client.patch(f"/api/series/{sid}/design", json={"style_id": style},
                                 headers=bearer(key, user))).json()
    bad = await client.patch(f"/api/series/{sid}/design", json={}, headers=bearer(key, user))

    assert themed["design"]["theme"] == "ciencia" and themed["design"]["palette"] == DESIGN["palette"]
    assert styled["design"]["style_id"] == style and styled["design"]["head_font"] == "Pacifico"
    assert bad.status_code == 422
    assert str(await raw_db.fetchval("select style_id from public.series where id = $1", sid)) == style


async def test_the_estimate_is_shown_before_creating(raw_db, google_user, client, key, engine):
    user = await google_user()

    quote = (await client.get("/api/estimate?sections=3&pages=12", headers=bearer(key, user))).json()
    bad = await client.get("/api/estimate?pages=2", headers=bearer(key, user))

    assert quote["sections"] == 3 and quote["pages"] == 12 and quote["currency"] == "USD"
    assert quote["total_usd"][0] < quote["total_usd"][1] and "history_usd" not in quote
    assert bad.status_code == 422
