"""The free book library on the landing, and the cover the user edits in the page editor."""

import json

from app.render import _write_pdf
from tests.db.test_covers import FakeStorage
from tests.db.test_jobs import engine  # noqa: F401 - a fixture
from tests.db.test_me import bearer
from tests.db.test_versions import _written


def _storage(app):
    storage = FakeStorage()

    async def signed_url(k, expires_in=60, download_name=None, bucket="exports"):
        return f"https://signed.test/{bucket}/{k}"

    async def download_private(k, bucket):
        return storage.uploads[(bucket, k)][0]

    storage.signed_url, storage.download_private = signed_url, download_private
    app.state.storage = storage
    return storage


async def test_an_admin_publishes_a_tome_as_a_free_book_downloaded_after_signing_in(raw_db, google_user, client, key,
                                                                                  engine):  # noqa: F811
    owner = await google_user()
    sid = await _written(raw_db, client, key, engine, owner)
    admin = await google_user(email="libros@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    storage = _storage(client._transport.app)

    early = await client.post("/api/admin/books", json={"series_id": str(sid)}, headers=bearer(key, admin))
    assert early.status_code == 409  # no PDF yet

    pdf, _ = _write_pdf("<html><body><p>Portada</p><p style='break-before: page'>Página 2</p></body></html>")
    storage.uploads[("exports", f"{owner}/{sid}/x.pdf")] = (pdf, "application/pdf")
    await raw_db.execute("""insert into public.exports (series_id, user_id, status, options, storage_key)
                            values ($1, $2, 'succeeded', '{}'::jsonb, $3)""", sid, owner, f"{owner}/{sid}/x.pdf")
    assert (await client.post("/api/admin/books", json={"series_id": str(sid)},
                              headers=bearer(key, owner))).status_code == 403  # admins only

    made = await client.post("/api/admin/books", json={"series_id": str(sid)}, headers=bearer(key, admin))
    assert made.status_code == 201
    book = made.json()["book"]
    slug = book["slug"]
    assert book["page_count"] == 2 and len(book["pages"]) == 2 and book["genre_label"] == "Cuento ilustrado"
    assert storage.uploads[("images", f"library/books/{slug}/0.jpg")][1] == "image/jpeg"

    listed = (await client.get("/api/books")).json()["books"]
    assert any(b["slug"] == slug for b in listed)
    assert (await client.get(f"/api/books/{slug}")).json()["book"]["title"] == book["title"]

    visitor = await google_user(anonymous=True)
    assert (await client.post(f"/api/books/{slug}/download", headers=bearer(key, visitor))).status_code == 401
    teacher = await google_user()
    got = await client.post(f"/api/books/{slug}/download", headers=bearer(key, teacher))
    assert got.status_code == 200 and got.json()["url"] == f"https://signed.test/exports/library/books/{slug}.pdf"

    gone = await client.delete(f"/api/admin/books/{sid}", headers=bearer(key, admin))
    assert gone.status_code == 204
    assert (await client.get(f"/api/books/{slug}")).status_code == 404
    await raw_db.execute("delete from public.library_books where series_id = $1", sid)


async def test_the_cover_prints_what_the_user_chose_besides_its_title(raw_db, google_user, client, key,
                                                                      engine):  # noqa: F811
    user = await google_user()
    sid = await _written(raw_db, client, key, engine, user)
    _storage(client._transport.app)

    saved = await client.patch(f"/api/series/{sid}/cover-options", headers=bearer(key, user),
                               json={"name_line": True, "kicker": "  Colección   Pequeños sabios ", "age": False})
    assert saved.status_code == 200
    assert saved.json()["cover_options"] == {"name_line": True, "kicker": "Colección Pequeños sabios", "age": False}
    back = await client.patch(f"/api/series/{sid}/cover-options", headers=bearer(key, user), json={"name_line": None})
    assert back.json()["cover_options"] == {"kicker": "Colección Pequeños sabios", "age": False}  # the default again
    assert json.loads(await raw_db.fetchval("select cover_options from public.series where id = $1", sid))["age"] is False

    preview = await client.get(f"/api/series/{sid}/cover/preview", headers=bearer(key, user))
    assert preview.status_code == 200 and preview.json()["image"].startswith("data:image/jpeg;base64,")
    filmed = await client.get(f"/api/series/{sid}/cover/preview?hd=true&name_line=false&age=false", headers=bearer(key, user))
    assert filmed.status_code == 200 and filmed.json()["image"] != preview.json()["image"]  # the marketing videos' cover

    asked = await client.post(f"/api/series/{sid}/cover", headers=bearer(key, user),
                              json={"instructions": "los personajes más grandes"})
    assert asked.status_code == 202
    payload = await raw_db.fetchval("""select payload from public.generation_jobs where series_id = $1 and kind = 'cover'
                                       order by created_at desc limit 1""", sid)
    assert json.loads(payload) == {"instructions": "los personajes más grandes"}
