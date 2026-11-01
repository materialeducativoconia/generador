"""The free preview: a landing visitor gets the outline, the cover and their small tome (up to 4 pages) written at
our cost; downloads and anything bigger need a plan, and signing in with Google carries the preview over."""

import json

from app.plans import FREE_PREVIEWS_PER_IP
from tests.db.conftest import subscribe
from tests.db.test_covers import FakeStorage
from tests.db.test_illustrations import ART, FakeImages, FakeVision
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


async def test_a_visitor_gets_the_whole_small_tome_free_and_nothing_more(raw_db, google_user, client, key, engine):
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
    jobs = await raw_db.fetch("select payload from public.generation_jobs where series_id = $1 and kind = 'lesson'", sid)
    sections = await raw_db.fetchval("select count(*) from public.lessons where series_id = $1", sid)
    assert len(jobs) == sections and all(json.loads(j["payload"]) == {"preview": True} for j in jobs)

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


async def test_the_preview_is_illustrated_like_the_real_tome_at_our_cost(raw_db, google_user, client, key, engine):
    await raw_db.execute("update public.assets set library = false")  # other tests' art: this one paints its own
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

    # The pages: written at our cost, then illustrated by the premium Illustrator, as the bought tome will be.
    job = await run_next(engine, ScriptedLLM(json.dumps(PICTURED_SECTION)))
    assert job["kind"] == "lesson" and job["payload"] == {"preview": True}
    job = await run_next(engine, ScriptedLLM(json.dumps(ART)), images=paid, storage=storage, vision=FakeVision())
    assert job["kind"] == "illustration" and job["payload"] == {"preview": True}
    assert paid.calls and {c["resolution"] for c in paid.calls} == {"1K"}  # drafts: thumbnails need no more
    assert await raw_db.fetchval("select bool_and(draft) and not bool_or(library) from public.assets"
                                 " where series_id = $1", sid)
    assert await raw_db.fetchval("select count(*) from public.credit_ledger l join public.memberships m using (org_id)"
                                 " where m.user_id = $1", anon) == 0  # on us

    # Bought: the full tome brings the premium cover, paid with credits.
    await subscribe(raw_db, anon, "docente", 40)
    assert (await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=h)).status_code == 202
    assert await raw_db.fetchval("select count(*) from public.generation_jobs where series_id = $1 and kind = 'cover'"
                                 " and status = 'queued' and payload = '{}'", sid) == 1

    # ...and the preview's 1K pictures go to print size for free and join the shared library.
    await raw_db.execute("update public.generation_jobs set status = 'cancelled' where series_id = $1 and kind <> 'illustration'", sid)
    job = await run_next(engine, ScriptedLLM(), images=paid, storage=storage, vision=FakeVision())
    assert job["kind"] == "illustration" and job["payload"] == {}
    rows = await raw_db.fetch("select draft, library, storage_key, media_type from public.assets where series_id = $1", sid)
    assert rows and all(not r["draft"] and r["library"] for r in rows)
    for r in rows:
        if r["media_type"] == "image/jpeg":
            assert r["storage_key"].endswith("-print.jpg") and ("images", r["storage_key"]) in storage.uploads


async def test_a_bought_preview_keeps_its_pages_and_charges_only_what_is_new(raw_db, google_user, client, key, engine):
    anon = await google_user(anonymous=True)
    h = visitor(key, anon, ip="203.0.113.80")
    sid = (await client.post("/api/series", json={**PREVIEW, "section_count": 2, "page_count": 2},
                             headers=h)).json()["series"]["id"]
    await run_next(engine, ScriptedLLM(json.dumps({**OUTLINE, "sections": OUTLINE["sections"][:2]})))
    await raw_db.execute("update public.generation_jobs set status = 'succeeded' where series_id = $1", sid)
    await raw_db.execute("update public.lessons set status = 'generated', content_json = $2::jsonb where series_id = $1",
                         sid, json.dumps(SECTION))
    await subscribe(raw_db, anon, "docente", 40)
    detail = (await client.get(f"/api/series/{sid}", headers=h)).json()
    lessons = [{k: l[k] for k in ("id", "title", "objectives", "key_points", "pages")} for l in detail["lessons"]]
    lessons.append({"title": "Una sección nueva", "objectives": ["Aprender más"], "key_points": ["más"], "pages": 3})

    edited = await client.patch(f"/api/series/{sid}/outline", headers=h,
                                json={"version": detail["version"], "lessons": lessons})
    assert edited.status_code == 200, edited.text
    assert (await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=h)).status_code == 202

    charged = await raw_db.fetch("select reason, delta from public.credit_ledger l join public.memberships m using (org_id)"
                                 " where m.user_id = $1 and delta < 0", anon)
    assert [(c["reason"], c["delta"]) for c in charged] == [("Sección", -3)]  # the new section only, not the 2 written


async def test_a_redone_outline_is_not_another_free_tome(raw_db, google_user, client, key, engine):
    anon = await google_user(anonymous=True)
    h = visitor(key, anon, ip="203.0.113.90")
    sid = (await client.post("/api/series", json=PREVIEW, headers=h)).json()["series"]["id"]
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))
    await raw_db.execute("delete from public.generation_jobs where series_id = $1 and kind <> 'outline'", sid)
    await subscribe(raw_db, anon, "docente", 40)  # a visitor cannot redo it at all (it costs credits); a buyer can

    assert (await client.post(f"/api/series/{sid}/outline/regenerate", json={}, headers=h)).status_code == 202
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))

    assert await raw_db.fetchval("select count(*) from public.generation_jobs where series_id = $1 and kind = 'lesson'",
                                 sid) == 0



async def test_a_preview_takes_matching_art_from_the_shared_library_for_free(raw_db, google_user, client, key, engine):
    await raw_db.execute("update public.assets set library = false")
    painter = await google_user()
    await raw_db.execute(
        """insert into public.assets (kind, subject, subject_norm, style_key, storage_key, media_type, created_by,
                                      library, aspect, topic_norm)
           values ('illustration', 'un granero rojo', 'granero rojo', 'tome:x', 'x.jpg', 'image/jpeg', $1, true, '4:3',
                   'granja')""", painter)
    anon = await google_user(anonymous=True)
    sid = (await client.post("/api/series", json={**PREVIEW, "section_count": 1, "page_count": 1},
                             headers=visitor(key, anon, ip="203.0.113.95"))).json()["series"]["id"]
    await run_next(engine, ScriptedLLM(json.dumps({**OUTLINE, "sections": OUTLINE["sections"][:1]})))
    only_barn = {**PICTURED_SECTION, "blocks": [b for b in PICTURED_SECTION["blocks"] if b["id"] != "b2"]}
    await run_next(engine, ScriptedLLM(json.dumps(only_barn)))

    paid = FakeImages()
    job = await run_next(engine, ScriptedLLM(), images=paid, storage=FakeStorage(), vision=FakeVision())

    assert job["kind"] == "illustration" and paid.calls == []  # not one picture painted
    content = json.loads(await raw_db.fetchval("select content_json from public.lessons where series_id = $1", sid))
    barn = next(b for b in content["blocks"] if b["id"] == "b3")
    assert await raw_db.fetchval("select subject from public.assets where id = $1::uuid", barn["asset_id"]) == "un granero rojo"


async def test_the_next_visitor_with_the_same_request_gets_the_finished_preview_at_no_cost(raw_db, google_user, client,
                                                                                         key, engine):
    first = await google_user(anonymous=True)
    request = {**PREVIEW, "request": "Libro ilustrado del ciclo del agua para preescolar"}
    donor = (await client.post("/api/series", json=request, headers=visitor(key, first, ip="203.0.113.97"))).json()
    sid = donor["series"]["id"]
    await raw_db.execute("update public.series set status = 'outline_ready', title = 'El agua', cover_key = 'c.png',"
                         " cover = '{\"free\": true}', design = $2::jsonb where id = $1", sid, json.dumps(DESIGN))
    await raw_db.execute("insert into public.lessons (series_id, position, title, objectives, key_points, content_json, status, pages)"
                         " values ($1, 1, 'Lluvia', '[]', '[]', $2::jsonb, 'generated', 1)", sid, json.dumps(SECTION))

    second = await google_user(anonymous=True)
    served = await client.post("/api/series", json={**request, "request": "  libro ILUSTRADO del ciclo del agua para preescolar"},
                               headers=visitor(key, second, ip="203.0.113.98"))

    assert served.status_code == 202 and served.json()["job"] is None
    copy = await raw_db.fetchrow("select status, title, cloned_from, user_id from public.series where id = $1::uuid",
                                 served.json()["series"]["id"])
    assert copy["status"] == "outline_ready" and copy["title"] == "El agua" and str(copy["cloned_from"]) == sid
    assert await raw_db.fetchval("select count(*) from public.lessons where series_id = $1 and status = 'generated'",
                                 served.json()["series"]["id"]) == 1
