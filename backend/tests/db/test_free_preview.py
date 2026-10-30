"""The free preview: a landing visitor gets the outline, the cover and a sample of section 1 at our cost; the rest
of the tome and the downloads need a plan, and signing in with Google carries the preview over."""

import json

from app.research import Photo
from tests.db.conftest import subscribe
from tests.db.test_covers import FakeStorage
from tests.db.test_illustrations import ART, LINE_ART, FakeImages, FakeVision
from tests.db.test_illustrations import SECTION as PICTURED_SECTION
from tests.db.test_jobs import OUTLINE, SECTION, engine, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.db.test_series_api import NEW_TOME
from tests.fakes import ScriptedLLM
from tests.test_covers import PLAN
from tests.test_themes import DESIGN


def visitor(key, user, ip="203.0.113.7"):
    return {**bearer(key, user), "X-Forwarded-For": f"{ip}, 10.0.0.1"}


async def test_a_visitor_gets_outline_cover_and_a_sample_free_and_nothing_more(raw_db, google_user, client, key,
                                                                               engine):
    anon = await google_user(anonymous=True)
    h = visitor(key, anon, ip="203.0.113.10")
    me = (await client.get("/api/me", headers=h)).json()
    assert me["anonymous"] is True and me["credits"] == 0

    created = await client.post("/api/series", json={**NEW_TOME, "section_count": 3, "page_count": 9}, headers=h)
    assert created.status_code == 202
    sid = created.json()["series"]["id"]
    assert await raw_db.fetchval("select count(*) from public.credit_ledger l join public.memberships m "
                                 "using (org_id) where m.user_id = $1", anon) == 0

    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))
    drawing = {"id": "b9", "type": "image", "kind": "line_art", "size": "full", "subject": "Un dragón amable"}
    llm = ScriptedLLM(json.dumps({**SECTION, "blocks": [*SECTION["blocks"], drawing]}))
    await run_next(engine, llm)  # the sample of section 1, queued by the outline job

    assert "es una muestra: escribe solo sus primeras 2 páginas" in json.dumps(llm.calls[0], ensure_ascii=False)
    lesson = await raw_db.fetchrow("select status, sample from public.lessons where series_id = $1 and position = 1",
                                   sid)
    assert dict(lesson) == {"status": "generated", "sample": True}
    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "outline_ready"
    assert await raw_db.fetchval("select count(*) from public.generation_jobs where series_id = $1"
                                 " and kind = 'illustration'", sid) == 1  # its drawings are painted right away

    again = await client.post("/api/series", json=NEW_TOME, headers=h)
    assert again.status_code == 402  # one free preview; after that, credits
    rest = await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=h)
    assert rest.status_code == 402
    checkout = await client.post("/api/billing/checkout", json={"plan": "docente"}, headers=h)
    assert checkout.status_code in (409, 503)


async def test_free_previews_are_capped_per_visitor(google_user, client, key):
    ip = "198.51.100.23"
    for _ in range(2):
        anon = await google_user(anonymous=True)
        assert (await client.post("/api/series", json=NEW_TOME, headers=visitor(key, anon, ip))).status_code == 202
    anon = await google_user(anonymous=True)
    third = await client.post("/api/series", json=NEW_TOME, headers=visitor(key, anon, ip))
    assert third.status_code == 429 and third.json()["error"]["code"] == "preview_limit"


async def test_signing_in_with_google_carries_the_preview_over(raw_db, google_user, client, key):
    anon = await google_user(anonymous=True)
    sid = (await client.post("/api/series", json=NEW_TOME,
                             headers=visitor(key, anon, ip="203.0.113.44"))).json()["series"]["id"]
    code = (await client.post("/api/claims", headers=bearer(key, anon))).json()["code"]

    teacher = await google_user(plan=None)
    moved = await client.post(f"/api/claims/{code}", headers=bearer(key, teacher))

    assert moved.json() == {"moved": 1}
    assert await raw_db.fetchval("select user_id from public.series where id = $1", sid) == teacher
    assert (await client.get(f"/api/series/{sid}", headers=bearer(key, teacher))).status_code == 200
    assert (await client.get("/api/me", headers=bearer(key, anon))).status_code == 403
    assert (await client.post(f"/api/claims/{code}", headers=bearer(key, teacher))).json() == {"moved": 0}
    # the real account's own free preview is spent too
    await raw_db.execute("update public.series set status = 'outline_ready' where id = $1", sid)
    assert (await client.post("/api/series", json=NEW_TOME, headers=bearer(key, teacher))).status_code == 402


class FakeFinder:
    """Openverse stand-in: it knows cows, nothing else."""

    def __init__(self):
        self.queries = []

    async def find(self, subject, kind, accept=None):
        self.queries.append((subject, kind))
        if "cow" not in subject or (accept and not await accept(LINE_ART)):
            return None
        return Photo(LINE_ART, "image/png", "Ana", "CC BY 4.0", "https://flickr.test/cow")


async def test_the_preview_pictures_cost_nothing(raw_db, google_user, client, key, engine):
    anon = await google_user(anonymous=True)
    h = visitor(key, anon, ip="203.0.113.61")
    sid = (await client.post("/api/series", json={**NEW_TOME, "section_count": 1, "page_count": 2},
                             headers=h)).json()["series"]["id"]
    await run_next(engine, ScriptedLLM(json.dumps({**OUTLINE, "sections": OUTLINE["sections"][:1]})), covers=True)
    paid, free, storage = FakeImages(), FakeImages(), FakeStorage()

    # The cover first (the sample waits its turn): the free Illustrator paints it, marked free.
    await raw_db.execute("update public.generation_jobs set run_after = now() + interval '1 hour'"
                         " where series_id = $1 and kind = 'lesson'", sid)
    job = await run_next(engine, ScriptedLLM(json.dumps(DESIGN), json.dumps(PLAN)), covers=True, images=paid,
                         free_images=free, storage=storage)
    assert job["kind"] == "cover"
    cover = json.loads(await raw_db.fetchval("select cover from public.series where id = $1", sid))
    assert cover["free"] is True and cover["spent_usd"] == 0 and len(free.calls) == 1

    await raw_db.execute("update public.generation_jobs set run_after = now() where series_id = $1", sid)
    await run_next(engine, ScriptedLLM(json.dumps(PICTURED_SECTION)))
    finder = FakeFinder()
    job = await run_next(engine, ScriptedLLM(json.dumps(ART)), images=paid, free_images=free, finder=finder,
                         storage=storage, vision=FakeVision())  # the Reviewer confirms the cow
    assert job["kind"] == "illustration" and paid.calls == []  # not one premium picture for the preview
    assets = await raw_db.fetch("select model, style_key, cost_usd, attribution from public.assets"
                                " where series_id = $1 order by model", sid)
    assert [(a["model"], a["style_key"], a["cost_usd"]) for a in assets] == [("fake-image", "free", 0.04),
                                                                             ("openverse", "free", 0)]
    assert json.loads(assets[1]["attribution"])["license"] == "CC BY 4.0"  # the Finder's picture is credited

    # Bought: the full tome brings the premium cover, paid with credits.
    await subscribe(raw_db, anon, "docente", 40)
    assert (await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=h)).status_code == 202
    assert await raw_db.fetchval("select count(*) from public.generation_jobs where series_id = $1 and kind = 'cover'"
                                 " and status = 'queued' and payload = '{}'", sid) == 1
