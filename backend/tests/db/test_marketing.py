"""/admin/marketing: DeepSeek writes a promotional video's script from a real tome; the team edits it."""

import json

from tests.db.test_jobs import engine  # noqa: F401 - a fixture
from tests.db.test_me import bearer
from tests.db.test_versions import _written
from tests.fakes import ScriptedLLM

SCRIPT = {"hook": "¿Otro domingo armando material?", "request": "Quiero un cuento sobre Lía y el águila para 6 años",
          "plan": "Jelyx arma el plan", "cover": "Pinta la portada", "pages": "Y cada página, ilustrada",
          "pdf": "Tu PDF, listo para imprimir", "cta": "Pruébalo gratis", "post": "Del tema al libro. #docentes",
          "voiceover": "¿Otro domingo armando material? Escribe tu tema y Jelyx hace el libro."}


async def test_the_team_gets_a_video_script_written_from_a_tome_and_edits_it(raw_db, google_user, client, key,
                                                                            engine):  # noqa: F811
    owner = await google_user()
    sid = await _written(raw_db, client, key, engine, owner)
    admin = await google_user(email="marketing@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    llm = ScriptedLLM(json.dumps(SCRIPT))
    client._transport.app.state.llm = llm

    assert (await client.post("/api/admin/marketing/videos", json={"series_id": str(sid)},
                              headers=bearer(key, owner))).status_code == 403
    made = await client.post("/api/admin/marketing/videos", json={"series_id": str(sid), "format": "16:9", "template": "topic_to_book"},
                             headers=bearer(key, admin))
    assert made.status_code == 201
    video = made.json()["video"]
    assert video["script"]["hook"] == SCRIPT["hook"] and video["format"] == "16:9"
    assert video["script"]["voiceover"] == SCRIPT["voiceover"]
    assert "Libro:" in llm.calls[0][-1]["content"]  # the tome's facts reach the scriptwriter

    edited = await client.patch(f"/api/admin/marketing/videos/{video['id']}", headers=bearer(key, admin),
                                json={"format": "9:16", "script": {**SCRIPT, "cta": "Haz tu libro gratis"}})
    assert edited.json()["video"]["script"]["cta"] == "Haz tu libro gratis" and edited.json()["video"]["format"] == "9:16"
    listed = (await client.get("/api/admin/marketing/videos", headers=bearer(key, admin))).json()["videos"]
    assert any(v["id"] == video["id"] for v in listed)
    assert (await client.delete(f"/api/admin/marketing/videos/{video['id']}", headers=bearer(key, admin))).status_code == 204


def test_a_script_line_a_little_too_long_is_cut_at_a_whole_word_not_rejected():
    from app.marketing import VideoScript

    script = VideoScript.model_validate({**SCRIPT, "hook": "¿Otro domingo armando material para tu clase de primaria? Hay otra forma"})

    assert script.hook == "¿Otro domingo armando material para tu clase de primaria?"


async def test_a_rendered_mp4_is_kept_for_downloading_again_until_the_script_changes(raw_db, google_user, client, key,
                                                                                   engine):  # noqa: F811
    owner = await google_user()
    sid = await _written(raw_db, client, key, engine, owner)
    admin = await google_user(email="marketing-mp4@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    app = client._transport.app
    app.state.llm = ScriptedLLM(json.dumps(SCRIPT))

    class Storage:
        async def upload_url(self, k, bucket):
            return f"https://upload.test/{bucket}/{k}"

        async def signed_url(self, k, expires_in=60, download_name=None, bucket="exports"):
            return f"https://signed.test/{bucket}/{k}?download={download_name}"

    app.state.storage = Storage()
    video = (await client.post("/api/admin/marketing/videos", json={"series_id": str(sid), "template": "topic_to_book"},
                               headers=bearer(key, admin))).json()["video"]
    vid = video["id"]
    assert video["has_mp4"] is False
    assert (await client.get(f"/api/admin/marketing/videos/{vid}/mp4", headers=bearer(key, admin))).status_code == 404

    up = (await client.post(f"/api/admin/marketing/videos/{vid}/upload", headers=bearer(key, admin))).json()
    assert up["upload_url"] == f"https://upload.test/marketing/{up['key']}" and up["key"].startswith(f"{vid}/")
    bad = await client.post(f"/api/admin/marketing/videos/{vid}/rendered", headers=bearer(key, admin),
                            json={"key": "00000000-0000-0000-0000-000000000000/abcdef12.mp4"})
    assert bad.status_code == 422  # another video's file
    done = await client.post(f"/api/admin/marketing/videos/{vid}/rendered", headers=bearer(key, admin), json={"key": up["key"]})
    assert done.json()["video"]["has_mp4"] is True
    got = (await client.get(f"/api/admin/marketing/videos/{vid}/mp4", headers=bearer(key, admin))).json()
    assert got["url"].startswith(f"https://signed.test/marketing/{up['key']}") and "jelyx-9x16" in got["url"]

    same = await client.patch(f"/api/admin/marketing/videos/{vid}", headers=bearer(key, admin), json={"format": "9:16"})
    assert same.json()["video"]["has_mp4"] is True  # nothing changed: the MP4 stays
    changed = await client.patch(f"/api/admin/marketing/videos/{vid}", headers=bearer(key, admin),
                                 json={"script": {**SCRIPT, "cta": "Otro cierre"}})
    assert changed.json()["video"]["has_mp4"] is False  # it showed the old words


BOARD = {"title": "Cómo editar las páginas de tu libro", "post": "Edita tu libro. #docentes", "scenes": [
    {"type": "editor_open", "seconds": 5, "caption": "Abre el Editor de páginas", "voice": "Abre el editor."},
    {"type": "editor_move", "seconds": 5, "caption": "Arrastra la pregunta", "voice": "Arrastra la pregunta."},
    {"type": "editor_facts", "seconds": 5, "caption": "Quita o añade datos", "voice": "Quita o añade datos."},
    {"type": "editor_save", "seconds": 5, "caption": "Guarda", "voice": "Y guarda."}]}


async def test_the_director_turns_a_request_into_a_tutorial_storyboard_of_the_apps_scenes(raw_db, google_user, client,
                                                                                         key, engine):  # noqa: F811
    owner = await google_user()
    sid = await _written(raw_db, client, key, engine, owner)
    admin = await google_user(email="director@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    llm = ScriptedLLM(json.dumps(BOARD))
    client._transport.app.state.llm = llm

    made = await client.post("/api/admin/marketing/videos", headers=bearer(key, admin), json={
        "series_id": str(sid), "ask": "Tutorial para editar páginas", "kind": "tutorial", "duration": 30})

    assert made.status_code == 201
    video = made.json()["video"]
    board = video["script"]
    assert video["template"] == "storyboard" and board["kind"] == "tutorial" and board["duration"] == 30
    assert "Tutorial para editar páginas" in llm.calls[0][-1]["content"] and "editor_move" in llm.calls[0][0]["content"]
    types = [s["type"] for s in board["scenes"]]
    assert types[0] == "title" and types[-1] == "cta"  # the code opens on a title and closes on the call to action
    assert types[1:-1] == ["editor_open", "editor_move", "editor_facts", "editor_save"]
    assert abs(sum(s["seconds"] for s in board["scenes"]) - 30) < 0.2  # exactly the length asked for
    assert board["scenes"][3]["text"]  # a typing scene always has something to type

    reordered = {**board, "scenes": [board["scenes"][0], board["scenes"][2], board["scenes"][1], *board["scenes"][3:]]}
    edited = await client.patch(f"/api/admin/marketing/videos/{video['id']}", headers=bearer(key, admin),
                                json={"script": reordered})
    assert [s["type"] for s in edited.json()["video"]["script"]["scenes"]][1:3] == ["editor_move", "editor_open"]
    bad = await client.patch(f"/api/admin/marketing/videos/{video['id']}", headers=bearer(key, admin),
                             json={"script": {**board, "scenes": [{"type": "explosion"}]}})
    assert bad.status_code == 422  # only scenes that exist


async def test_a_storyboard_is_proposed_seen_and_asked_again_before_the_video_is_made(raw_db, google_user, client,
                                                                                     key, engine):  # noqa: F811
    owner = await google_user()
    sid = await _written(raw_db, client, key, engine, owner)
    admin = await google_user(email="proposal@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    llm = ScriptedLLM(json.dumps(BOARD), json.dumps(BOARD))
    client._transport.app.state.llm = llm
    ask = {"series_id": str(sid), "ask": "Anuncio para mamás", "kind": "marketing", "duration": 15}

    kinds = (await client.get("/api/admin/marketing/structures", headers=bearer(key, admin))).json()["structures"]
    assert {"antes_despues", "pasos"} <= {s["key"] for s in kinds}
    first = (await client.post("/api/admin/marketing/storyboard", headers=bearer(key, admin),
                               json={**ask, "structure": "antes_despues"})).json()["script"]
    assert first["structure"] == "antes_despues" and first["look"] in ("claro", "oscuro", "color")
    assert "Antes y después" in llm.calls[0][-1]["content"]
    assert "personajes" in llm.calls[0][-1]["content"].lower()  # the director knows whether the book has a cast
    listed = (await client.get("/api/admin/marketing/videos", headers=bearer(key, admin))).json()["videos"]
    assert not any(v["series_id"] == str(sid) for v in listed)  # not saved

    made = await client.post("/api/admin/marketing/videos", headers=bearer(key, admin),
                             json={**ask, "script": {**first, "title": "Mi título"}})
    assert made.status_code == 201 and made.json()["video"]["script"]["title"] == "Mi título"
    assert len(llm.calls) == 1  # the reviewed storyboard is kept as it is, not asked again

    again = (await client.post("/api/admin/marketing/storyboard", headers=bearer(key, admin), json=ask)).json()["script"]
    assert again["structure"] != "antes_despues"  # automatic: not the structure the last video used
    assert "Mi título" in llm.calls[1][-1]["content"]  # told the videos already made, to tell this one another way
    assert (await client.post("/api/admin/marketing/storyboard", headers=bearer(key, admin),
                              json={**ask, "structure": "nada"})).status_code == 422


def test_a_video_may_open_on_the_finished_book_instead_of_a_title():
    from app.marketing import Storyboard, tidy_storyboard

    board = tidy_storyboard(Storyboard.model_validate({"title": "x y", "scenes": [
        {"type": "pdf", "caption": "Esto lo hice en 5 minutos"}, {"type": "versus"}, {"type": "number"}]}))

    assert [s.type for s in board.scenes] == ["pdf", "versus", "number", "cta"]
    assert board.scenes[1].text and board.scenes[2].text


async def test_real_screenshots_are_kept_with_their_zoom_points_and_the_director_shows_them(raw_db, google_user, client,
                                                                                           key, engine):  # noqa: F811
    owner = await google_user()
    sid = await _written(raw_db, client, key, engine, owner)
    admin = await google_user(email="captures@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    app = client._transport.app
    deleted = []

    class Storage:
        async def upload_url(self, k, bucket):
            return f"https://upload.test/{bucket}/{k}"

        async def signed_urls(self, keys, bucket, expires_in=3600):
            return {k: f"https://signed.test/{bucket}/{k}" for k in keys}

        async def delete(self, k, bucket):
            deleted.append(k)

    app.state.storage = Storage()
    up = (await client.post("/api/admin/marketing/captures/upload?ext=png", headers=bearer(key, admin))).json()
    made = (await client.post("/api/admin/marketing/captures", headers=bearer(key, admin),
                              json={"key": up["key"], "name": "Editor de páginas", "width": 1440, "height": 900})).json()
    cap = made["capture"]
    assert cap["url"] == f"https://signed.test/marketing/{up['key']}" and cap["focus"] == []
    edited = (await client.patch(f"/api/admin/marketing/captures/{cap['id']}", headers=bearer(key, admin), json={
        "description": "la tira de páginas y el formulario", "focus": [{"x": 0.7, "y": 0.4, "label": "Añadir dato"}]})).json()
    assert edited["capture"]["focus"][0]["label"] == "Añadir dato"

    board = {**BOARD, "scenes": [*BOARD["scenes"], {"type": "screen", "capture": cap["id"], "focus": 5, "caption": "Así"},
                                 {"type": "screen", "capture": "inventada", "caption": "No"}]}
    llm = ScriptedLLM(json.dumps(board))
    app.state.llm = llm
    script = (await client.post("/api/admin/marketing/storyboard", headers=bearer(key, admin), json={
        "series_id": str(sid), "kind": "tutorial"})).json()["script"]
    assert f"{cap['id']}: Editor de páginas" in llm.calls[0][-1]["content"] and "0 Añadir dato" in llm.calls[0][-1]["content"]
    screens = [s for s in script["scenes"] if s["type"] == "screen"]
    assert [(s["capture"], s["focus"]) for s in screens] == [(cap["id"], 0)]  # a made-up capture is dropped, the point kept in range

    assert (await client.delete(f"/api/admin/marketing/captures/{cap['id']}", headers=bearer(key, admin))).status_code == 204
    assert deleted == [up["key"]]
