"""The style lab: admins paint one subject in every house style and keep the best samples as references."""

import asyncio

from app.house_styles import STYLES
from tests.db.test_admin import bearer
from tests.db.test_covers import FakeImages, FakeStorage
from tests.test_covers import PNG as PNG_JPEG


async def test_admins_paint_a_subject_in_every_style_and_keep_one(raw_db, google_user, client, key):
    admin = await google_user(email="estilos@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    app = client._transport.app
    app.state.images, app.state.storage = FakeImages(), FakeStorage()

    response = await client.post("/api/admin/style-lab", json={"subject": "un colibrí junto a una flor"},
                                 headers=bearer(key, admin))
    assert response.status_code == 202
    for _ in range(100):
        body = (await client.get("/api/admin/style-lab", headers=bearer(key, admin))).json()
        run = next(r for r in body["runs"] if r["run"] == response.json()["run"])
        if all(s["status"] != "painting" for s in run["samples"]):
            break
        await asyncio.sleep(0.05)

    assert [s["style"] for s in run["samples"]] == [s.key for s in STYLES]
    assert all(s["status"] == "done" and s["url"] and s["raw_url"] for s in run["samples"])
    assert all("colibrí" in c["prompt"] and "Larousse" not in c["prompt"] for c in app.state.images.calls)
    sample = run["samples"][0]["id"]
    kept = await client.patch(f"/api/admin/style-lab/{sample}", json={"chosen": True}, headers=bearer(key, admin))
    assert kept.status_code == 200


async def test_the_style_lab_is_for_admins(google_user, client, key):
    user = await google_user()
    response = await client.post("/api/admin/style-lab", json={"subject": "x"}, headers=bearer(key, user))
    assert response.status_code in (403, 503)
    assert (await client.get("/api/admin/style-lab", headers=bearer(key, user))).status_code == 403


async def test_a_failed_style_is_painted_again_alone(raw_db, google_user, client, key):
    admin = await google_user(email="reintento@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    app = client._transport.app
    images, failing = FakeImages(), {"collage"}
    real = images.generate

    async def generate(prompt, **kw):
        if failing and "Cut-paper" in prompt:
            raise RuntimeError("OpenRouter 403: Key limit exceeded")
        return await real(prompt, **kw)

    images.generate = generate
    app.state.images, app.state.storage = images, FakeStorage()

    async def settled():
        for _ in range(100):
            body = (await client.get("/api/admin/style-lab", headers=bearer(key, admin))).json()
            found = next(r for r in body["runs"] if r["run"] == run)
            if all(s["status"] != "painting" for s in found["samples"]):
                return {s["style"]: s["status"] for s in found["samples"]}
            await asyncio.sleep(0.05)

    run = (await client.post("/api/admin/style-lab", json={"subject": "un búho", "styles": ["collage", "gouache"]},
                             headers=bearer(key, admin))).json()["run"]
    assert await settled() == {"collage": "failed", "gouache": "done"}
    failing.clear()
    painted = len(images.calls)
    retry = await client.post(f"/api/admin/style-lab/{run}/retry", headers=bearer(key, admin))
    assert retry.json()["styles"] == ["collage"]
    assert await settled() == {"collage": "done", "gouache": "done"}
    assert len(images.calls) == painted + 1


async def test_a_lab_sample_becomes_a_free_plate_downloaded_after_signing_in(raw_db, google_user, client, key):
    admin = await google_user(email="biblioteca@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    app = client._transport.app
    storage = FakeStorage()
    storage.uploads[("images", "style-lab/x/acuarela.jpg")] = (PNG_JPEG, "image/jpeg")

    async def signed_url(k, expires_in=60, download_name=None, bucket="exports"):
        return f"https://signed.test/{bucket}/{k}"

    storage.signed_url = signed_url
    app.state.storage = storage
    sample = await raw_db.fetchval("""insert into public.style_samples (run, style, subject, status, key)
        values (gen_random_uuid(), 'acuarela', 'el sol', 'done', 'style-lab/x/acuarela.jpg') returning id""")

    made = await client.post("/api/admin/library", json={
        "sample_id": str(sample), "title": "¿Por qué brilla el Sol?", "answer": "Porque es una estrella.",
        "topic": "El sistema solar"}, headers=bearer(key, admin))
    assert made.status_code == 201
    slug = made.json()["plate"]["slug"]
    assert slug.startswith("por-que-brilla-el-sol")

    listed = (await client.get("/api/library?topic=El%20sistema%20solar")).json()
    assert any(p["slug"] == slug and p["style_name"] == "Acuarela y tinta" for p in listed["plates"])
    assert (await client.get(f"/api/library/{slug}")).json()["plate"]["title"] == "¿Por qué brilla el Sol?"

    visitor = await google_user(anonymous=True)
    assert (await client.post(f"/api/library/{slug}/download", headers=bearer(key, visitor))).status_code == 401
    teacher = await google_user()
    got = await client.post(f"/api/library/{slug}/download", headers=bearer(key, teacher))
    assert got.status_code == 200 and got.json()["url"].endswith(f"library/{slug}.pdf")
    assert storage.uploads[("exports", f"library/{slug}.pdf")][0].startswith(b"%PDF")
    await raw_db.execute("delete from public.library_plates where slug = $1", slug)
