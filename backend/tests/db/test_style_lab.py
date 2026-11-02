"""The style lab: admins paint one subject in every house style and keep the best samples as references."""

import asyncio

from app.house_styles import STYLES
from tests.db.test_admin import bearer
from tests.db.test_covers import FakeImages, FakeStorage


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
