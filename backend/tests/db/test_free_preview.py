"""The free preview: a landing visitor gets the outline, the cover and a sample of section 1 at our cost; the rest
of the tome and the downloads need a plan, and signing in with Google carries the preview over."""

import json

from app.llm import UpstreamError
from app.plans import FREE_PREVIEWS_PER_IP
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


PREVIEW = {**NEW_TOME, "page_count": 4}  # a visitor's preview: up to 4 pages and 4 sections


def visitor(key, user, ip="203.0.113.7"):
    return {**bearer(key, user), "X-Forwarded-For": f"{ip}, 10.0.0.1"}


async def test_a_visitor_gets_outline_and_cover_free_and_nothing_more(raw_db, google_user, client, key,
                                                                               engine):
    anon = await google_user(anonymous=True)
    h = visitor(key, anon, ip="203.0.113.10")
    me = (await client.get("/api/me", headers=h)).json()
    assert me["anonymous"] is True and me["credits"] == 0 and me["free_preview"] is True

    too_big = await client.post("/api/series", json={**NEW_TOME, "section_count": 3, "page_count": 9}, headers=h)
    assert too_big.status_code == 403 and too_big.json()["error"]["details"]["max_pages"] == 4
    created = await client.post("/api/series", json={**NEW_TOME, "section_count": 3, "page_count": 4}, headers=h)
    assert created.status_code == 202
    sid = created.json()["series"]["id"]
    assert await raw_db.fetchval("select count(*) from public.credit_ledger l join public.memberships m "
                                 "using (org_id) where m.user_id = $1", anon) == 0

    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))
    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "outline_ready"
    assert await raw_db.fetchval("select count(*) from public.generation_jobs where series_id = $1"
                                 " and kind = 'lesson'", sid) == 0  # only the cover: the pages show blurred

    again = await client.post("/api/series", json=NEW_TOME, headers=h)
    assert again.status_code == 402  # one free preview; after that, credits
    assert (await client.get("/api/me", headers=h)).json()["free_preview"] is False
    rest = await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=h)
    assert rest.status_code == 402
    checkout = await client.post("/api/billing/checkout", json={"plan": "docente"}, headers=h)
    assert checkout.status_code in (409, 503)


async def test_free_previews_are_capped_per_visitor(raw_db, google_user, client, key):
    ip = "198.51.100.23"  # what Supabase Auth saw; each request below forges another X-Forwarded-For
    for n in range(FREE_PREVIEWS_PER_IP + 1):
        anon = await google_user(anonymous=True)
        await raw_db.execute("insert into auth.sessions (id, user_id, created_at, updated_at, ip)"
                             " values (gen_random_uuid(), $1, now(), now(), $2::inet)", anon, ip)
        response = await client.post("/api/series", json=PREVIEW, headers=visitor(key, anon, f"192.0.2.{n}"))
    assert response.status_code == 429 and response.json()["error"]["code"] == "preview_limit"


async def test_signing_in_with_google_carries_the_preview_over(raw_db, google_user, client, key):
    anon = await google_user(anonymous=True)
    sid = (await client.post("/api/series", json=PREVIEW,
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


class BusyIllustrator(FakeImages):
    """The free Illustrator, out of its daily allowance for cows."""

    async def generate(self, prompt, **kw):
        if "cow" in prompt:
            raise UpstreamError("upstream_unavailable", "Workers AI respondió 429.")
        return await super().generate(prompt, **kw)


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
    await raw_db.execute("delete from public.assets where style_key = 'free'")  # an earlier run fills the library
    anon = await google_user(anonymous=True)
    h = visitor(key, anon, ip="203.0.113.61")
    sid = (await client.post("/api/series", json={**PREVIEW, "section_count": 1, "page_count": 2},
                             headers=h)).json()["series"]["id"]
    await run_next(engine, ScriptedLLM(json.dumps({**OUTLINE, "sections": OUTLINE["sections"][:1]})), covers=True)
    paid, free, storage = FakeImages(), FakeImages(), FakeStorage()

    # The cover: the free Illustrator paints it, marked free.
    job = await run_next(engine, ScriptedLLM(json.dumps(DESIGN), json.dumps(PLAN)), covers=True, images=paid,
                         free_images=free, storage=storage)
    assert job["kind"] == "cover"
    cover = json.loads(await raw_db.fetchval("select cover from public.series where id = $1", sid))
    assert cover["free"] is True and cover["spent_usd"] == 0 and len(free.calls) == 1

    # A sample of the first pages (no longer shown to visitors) still gets its pictures for free.
    await raw_db.execute("insert into public.generation_jobs (user_id, series_id, lesson_id, kind, status, payload)"
                         " select $1, $2, id, 'lesson', 'queued', '{\"sample_pages\": 2}' from public.lessons"
                         " where series_id = $2 and position = 1", anon, sid)
    await run_next(engine, ScriptedLLM(json.dumps(PICTURED_SECTION)))
    finder = FakeFinder()  # the fallback when the free Illustrator cannot paint
    job = await run_next(engine, ScriptedLLM(json.dumps(ART)), images=paid, free_images=BusyIllustrator(),
                         finder=finder, storage=storage, vision=FakeVision())  # the Reviewer confirms the cow
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
