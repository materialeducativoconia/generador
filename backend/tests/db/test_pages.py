"""Editor de páginas: a page seen as the PDF prints it, its words edited by hand, its picture painted again."""

import json
from unittest.mock import patch

from tests.db.test_jobs import engine  # noqa: F401 - a fixture
from tests.db.test_me import bearer
from tests.db.test_versions import _written


async def _lesson(raw_db, sid):
    return await raw_db.fetchval("select id from public.lessons where series_id = $1", sid)


async def test_the_page_text_is_edited_by_hand(raw_db, google_user, client, key, engine):  # noqa: F811
    user = await google_user()
    sid = await _written(raw_db, client, key, engine, user)
    lid = await _lesson(raw_db, sid)

    response = await client.patch(f"/api/lessons/{lid}/pages/p1", headers=bearer(key, user),
                                  json={"narration": "  Lía miró el cielo y vio un águila.  ", "layout": "band"})

    assert response.status_code == 200
    row = await raw_db.fetchrow("select status, content_version, content_json from public.lessons where id = $1", lid)
    block = json.loads(row["content_json"])["blocks"][0]
    assert row["status"] == "edited" and row["content_version"] >= 1
    assert block["narration"] == "Lía miró el cielo y vio un águila." and block["layout"] == "band"
    assert block["asset_id"]  # the picture stays


async def test_one_picture_is_painted_again_with_the_users_instruction(raw_db, google_user, client, key,
                                                                       engine):  # noqa: F811
    user = await google_user()
    sid = await _written(raw_db, client, key, engine, user)
    lid = await _lesson(raw_db, sid)
    await raw_db.execute("""update public.series set art = '{"style": "x", "prompts": {"1:p1": "old"}}'::jsonb
                             where id = $1""", sid)

    response = await client.post(f"/api/lessons/{lid}/pages/p1/repaint", headers=bearer(key, user),
                                 json={"instructions": "que Lía mire hacia arriba"})

    assert response.status_code == 202
    block = json.loads(await raw_db.fetchval("select content_json from public.lessons where id = $1", lid))["blocks"][0]
    assert "asset_id" not in block and block["subject"].endswith("(Cambio pedido por el usuario: que Lía mire hacia arriba)")
    assert json.loads(await raw_db.fetchval("select art from public.series where id = $1", sid))["prompts"] == {}
    assert await raw_db.fetchval(
        "select count(*) from public.generation_jobs where series_id = $1 and kind = 'illustration' and status = 'queued'",
        sid) == 1


async def test_the_preview_is_the_printed_page(raw_db, google_user, client, key, engine):  # noqa: F811
    user = await google_user()
    sid = await _written(raw_db, client, key, engine, user)
    lid = await _lesson(raw_db, sid)

    response = await client.get(f"/api/lessons/{lid}/pages/p1/preview", headers=bearer(key, user))

    assert response.status_code == 200 and response.json()["image"].startswith("data:image/jpeg;base64,")
    # Coming back to the same page does not lay it out again.
    with patch("app.api.pages._render_page", side_effect=AssertionError("rendered twice")):
        again = await client.get(f"/api/lessons/{lid}/pages/p1/preview", headers=bearer(key, user))
    assert again.json() == response.json()


async def test_texts_dragged_on_the_page_print_where_the_user_left_them(raw_db, google_user, client, key,
                                                                         engine):  # noqa: F811
    from app.content import Image
    from app.render import Tome, TomeSection, render_html
    from app.content import SectionContent

    user = await google_user()
    sid = await _written(raw_db, client, key, engine, user)
    lid = await _lesson(raw_db, sid)

    response = await client.patch(f"/api/lessons/{lid}/pages/p1", headers=bearer(key, user),
                                  json={"place": {"q": {"x": 0, "y": 62.5}}})
    assert response.status_code == 200 and response.json()["block"]["place"] == {"q": {"x": 0, "y": 62.5}}
    bad = await client.patch(f"/api/lessons/{lid}/pages/p1", headers=bearer(key, user),
                             json={"place": {"q": {"x": 0, "y": 140}}})
    assert bad.status_code == 422  # never off the page

    block = Image.model_validate({"id": "b1", "type": "image", "kind": "illustration", "size": "plate", "subject": "x",
                                  "question": "¿Qué?", "notes": ["uno", "dos"], "find": "¿dónde?",
                                  "place": {"q": {"x": 0, "y": 60}, "f": {"x": 0, "y": 5}, "n1": {"x": 33, "y": 44}}})
    html = render_html(Tome(title="t", genre="picture_book", audience="", author=None,
                            sections=[TomeSection(1, "s", SectionContent(blocks=[block]))]),
                       paper="17x21", include_answer_key=False)
    assert 'class="pq" style="top: 60.0%"' in html and "top: 5.0%; bottom: auto" in html
    assert 'class="pn at" style="left: 33.0%; top: 44.0%">dos' in html

    cleared = await client.patch(f"/api/lessons/{lid}/pages/p1", headers=bearer(key, user), json={"place": {}})
    assert "place" not in cleared.json()["block"]  # back to the automatic layout
