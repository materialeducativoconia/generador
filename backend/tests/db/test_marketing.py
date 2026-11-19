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
    assert first["structure"] == "antes_despues" and first["look"] in ("claro", "oscuro", "color", "noche")
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


async def test_the_voiceover_is_read_scene_by_scene_and_an_unchanged_line_is_not_paid_again(raw_db, google_user, client,
                                                                                            key, engine):  # noqa: F811
    from app.voice import seconds, wav

    owner = await google_user()
    sid = await _written(raw_db, client, key, engine, owner)
    admin = await google_user(email="voice@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    app = client._transport.app

    class Storage:
        files: dict[str, bytes] = {}

        async def upload(self, k, data, content_type="application/pdf", bucket="exports"):
            self.files[k] = data

        async def signed_urls(self, keys, bucket, expires_in=3600):
            return {k: f"https://signed.test/{bucket}/{k}" for k in keys if k in self.files}

    class Voice:
        model, voice, said = "google/gemini-tts", "Kore", []

        async def speak(self, words, **_):
            self.said.append(words)
            return wav(b"\0\0" * 24_000)  # one second

    app.state.storage, app.state.voice = Storage(), Voice()
    board = {**BOARD, "scenes": [*BOARD["scenes"][:3], {**BOARD["scenes"][3], "voice": ""}]}
    saved = (await client.post("/api/admin/marketing/videos", headers=bearer(key, admin), json={
        "series_id": str(sid), "script": board})).json()["video"]
    vid, scenes = saved["id"], saved["script"]["scenes"]

    clips = (await client.post(f"/api/admin/marketing/videos/{vid}/voice", headers=bearer(key, admin))).json()["clips"]
    assert [c["scene"] for c in clips] == [i for i, sc in enumerate(scenes) if sc["voice"]]  # a silent scene gets no clip
    assert all(c["url"].startswith(f"https://signed.test/marketing/{vid}/voice/") and c["seconds"] == 1 for c in clips)
    assert app.state.voice.said == ["Abre el editor.", "Arrastra la pregunta.", "Quita o añade datos."]
    assert seconds(next(iter(Storage.files.values()))) == 1

    first = clips[0]["scene"]
    edited = {**saved["script"], "scenes": [*scenes[:first], {**scenes[first], "voice": "Abre tu libro."}, *scenes[first + 1:]]}
    await client.patch(f"/api/admin/marketing/videos/{vid}", headers=bearer(key, admin), json={"script": edited})
    again = (await client.post(f"/api/admin/marketing/videos/{vid}/voice", headers=bearer(key, admin))).json()["clips"]
    assert len(again) == 3 and app.state.voice.said[3:] == ["Abre tu libro."]  # only the changed line is read again
    assert (await client.post(f"/api/admin/marketing/videos/{vid}/voice", headers=bearer(key, owner))).status_code == 403


async def test_a_voice_longer_than_its_scene_is_written_again_shorter_by_the_director():
    from app.marketing import director

    long = {"title": "Tu libro en un minuto", "post": "#docentes", "scenes": [
        {"type": "title", "seconds": 2, "caption": "Tu libro en un minuto", "voice": "¿Conocías la app que hace un libro ilustrado completo en un minuto?"},
        {"type": "pages", "seconds": 10, "caption": "Las páginas", "voice": "Mira sus páginas."},
        {"type": "cta", "seconds": 3, "caption": "Pruébalo", "voice": "Pruébalo gratis."}]}
    llm = ScriptedLLM(json.dumps(long), json.dumps({"voices": ["¿Un libro en un minuto?", "Mira sus páginas.", "Pruébalo gratis."]}))

    board = (await director(llm, ask="Gancho", kind="marketing", duration=15, title="Felinos", topic="felinos",
                            book_kind="Libro", audience="", sections=[], sample=None, structure=pick())).value

    assert [s.voice for s in board.scenes] == ["¿Un libro en un minuto?", "Mira sus páginas.", "Pruébalo gratis."]
    assert "escena 1 (2 s): 12 palabras, máximo 5" in llm.calls[1][-1]["content"]

    fits = ScriptedLLM(json.dumps({**long, "scenes": [{**long["scenes"][0], "voice": "¿Un libro en un minuto?"}, *long["scenes"][1:]]}))
    await director(fits, ask="Gancho", kind="marketing", duration=15, title="Felinos", topic="felinos",
                   book_kind="Libro", audience="", sections=[], sample=None, structure=pick())
    assert len(fits.calls) == 1  # a voice that fits is not asked again


def pick():
    from app.marketing import pick_structure
    return pick_structure("marketing")


async def test_a_motion_graphics_video_draws_what_deepseek_designed_from_the_request():
    from app.marketing import director

    board = {"title": "Tu selva en minutos", "post": "#docentes", "scenes": [
        {"type": "motion", "seconds": 3, "caption": "Tu tema", "text": "De un tema a un libro", "voice": "",
         "motion": {"style": "orbit", "colors": ["#2f8f4e", "verde", "#c98a12"],
                    "items": [{"icon": "leaf", "label": "Selva"}, {"icon": "dragon", "label": "Animales"}]}},
        {"type": "motion", "seconds": 3, "caption": "Cómo se hace", "voice": "", "motion": {"style": "spiral"}},
        {"type": "pages", "seconds": 4, "caption": "Las páginas", "voice": "", "motion": {"style": "flow"}},
        {"type": "cta", "seconds": 3, "caption": "Pruébalo", "voice": ""}]}
    llm = ScriptedLLM(json.dumps(board))

    made = (await director(llm, ask="motion graphics de la selva", kind="motion", duration=15, title="Selva",
                           topic="selva", book_kind="Libro", audience="", sections=[], sample=None,
                           structure="motion_explica")).value

    prompt = llm.calls[0][0]["content"]
    assert "La escena motion es un motion graphic que diseñas tú" in prompt and "Diséñalo a partir del pedido" in prompt and "orbit" in prompt
    first, second, pages = made.scenes[:3]
    assert first.motion.style == "orbit" and first.motion.colors == ["#2f8f4e", "#c98a12"]  # a bad colour is dropped
    assert [i.icon for i in first.motion.items] == ["leaf", "sparkle"]  # an unknown icon becomes the sparkle
    assert second.motion.style == "burst" and second.motion.items  # never an empty graphic
    assert pages.motion is None and made.kind == "motion"


async def test_a_video_is_made_from_the_teams_own_script_its_words_read_as_written(raw_db, google_user, client, key,
                                                                                    engine):  # noqa: F811
    owner = await google_user()
    sid = await _written(raw_db, client, key, engine, owner)
    admin = await google_user(email="guion@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    script = ("Gancho: ¿Otro domingo armando material?\n\n"
              "[portada] Escribes el tema de tu clase y en cinco minutos tienes un libro ilustrado.\n\n"
              "[motion órbita] Mismos personajes en todas las páginas.\n\n"
              "Pruébalo gratis en docs.jelyx.app")
    designed = {"title": "Tu domingo libre", "post": "Tu clase lista. #docentes", "scenes": [  # one scene short
        {"type": "title", "caption": "¿Otro domingo así?"}, {"type": "pages", "caption": "Tu libro"},
        {"type": "motion", "caption": "Mismos personajes", "motion": {"style": "flow", "items": [{"icon": "people", "label": "Lía"}]}}]}
    llm = ScriptedLLM(json.dumps(designed))
    client._transport.app.state.llm = llm
    asked = {"series_id": str(sid), "kind": "motion", "script_text": script, "music": "wallpaper"}

    board = (await client.post("/api/admin/marketing/storyboard", headers=bearer(key, admin), json=asked)).json()["script"]

    told = llm.calls[0][-1]["content"]
    assert "Guion (4 escenas)" in told and "(tipo fijado: motion orbit)" in told
    scenes = board["scenes"]
    assert [s["voice"] for s in scenes] == ["¿Otro domingo armando material?",  # the label is not read
                                            "Escribes el tema de tu clase y en cinco minutos tienes un libro ilustrado.",
                                            "Mismos personajes en todas las páginas.", "Pruébalo gratis en docs.jelyx.app"]
    assert [s["type"] for s in scenes] == ["title", "cover", "motion", "motion"]  # the marks win; a missing one is drawn
    assert scenes[2]["motion"]["style"] == "orbit" and scenes[3]["motion"]["items"]
    assert board["source"] == "script" and scenes[1]["seconds"] > scenes[0]["seconds"]  # as long as its words take
    beat = 60 / 124
    cuts, at = [], 0.0
    for s in scenes:
        at += s["seconds"]
        cuts.append(at)
    assert all(abs(((c - 0.02) / beat) - round((c - 0.02) / beat)) < 0.01 for c in cuts)  # every cut on a beat
    assert "Kevin MacLeod" in board["post"]  # the music's credit

    made = await client.post("/api/admin/marketing/videos", headers=bearer(key, admin), json={**asked, "script": board})
    assert made.status_code == 201 and made.json()["video"]["script"]["scenes"] == scenes  # saved as it was seen

    long = "\n".join(f"Línea {i}" for i in range(30))
    too_long = await client.post("/api/admin/marketing/storyboard", headers=bearer(key, admin), json={**asked, "script_text": long})
    assert too_long.status_code == 422 and "máximo es 24" in too_long.json()["error"]["message"]


def test_the_voice_reads_the_address_spelled_out():
    from app.api.marketing import said

    assert said("Entra a https://docs.jelyx.app/ hoy") == "Entra a docs punto jelyx punto app hoy"


async def test_claude_programs_a_scene_a_medida_and_a_forbidden_reply_is_asked_again(raw_db, google_user, client, key):
    import httpx

    from app.coder import SceneCoder, problem

    admin = await google_user(email="medida@jelyx.test")
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    good = "function Scene({ frame, dur, look, caption }) {\n  return <AbsoluteFill style={{ opacity: frame / dur }}>{caption}</AbsoluteFill>\n}"
    replies = ["```jsx\nfunction Scene() { return <img src='x' /> }\n```", f"Aquí está:\n```jsx\n{good}\n```"]
    asked = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": replies[len(asked) - 1]}}], "usage": {"cost": 0.05}})

    app = client._transport.app
    app.state.coder = SceneCoder("k", ["anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5"], transport=httpx.MockTransport(answer))
    board = {"title": "Tu domingo libre", "look": "noche", "scenes": [
        {"type": "title", "seconds": 3, "caption": "¿Otro domingo así?", "voice": "¿Otro domingo armando material?"},
        {"type": "cta", "seconds": 3, "caption": "Pruébalo gratis"}]}

    listed = (await client.get("/api/admin/marketing/structures", headers=bearer(key, admin))).json()["coders"]
    assert listed == [{"key": "anthropic/claude-opus-5.5", "label": "Claude Opus 5.5"},
                      {"key": "anthropic/claude-sonnet-5.5", "label": "Claude Sonnet 5.5"}]
    out = await client.post("/api/admin/marketing/scene-code", headers=bearer(key, admin),
                            json={"board": board, "index": 0, "model": "anthropic/claude-sonnet-5.5", "format": "1:1"})
    assert out.status_code == 200, out.text
    assert out.json() == {"code": good, "model": "anthropic/claude-sonnet-5.5", "cost": 0.1}
    assert len(asked) == 2 and asked[0]["model"] == "anthropic/claude-sonnet-5.5"
    assert "1080×1080" in asked[0]["messages"][0]["content"] and "#08071a" in asked[0]["messages"][1]["content"]
    assert "▶ 1. title" in asked[0]["messages"][1]["content"]
    assert "etiqueta que no está permitida" in asked[1]["messages"][-1]["content"]  # told why, once

    board["scenes"][0]["code"] = good  # a change rewrites the current code
    replies.append(f"```jsx\n{good}\n```")
    await client.post("/api/admin/marketing/scene-code", headers=bearer(key, admin),
                      json={"board": board, "index": 0, "change": "más dinámica"})
    assert asked[2]["model"] == "anthropic/claude-opus-5.5" and "más dinámica" in asked[2]["messages"][-1]["content"]
    assert good in asked[2]["messages"][-1]["content"]

    wrong = await client.post("/api/admin/marketing/scene-code", headers=bearer(key, admin),
                              json={"board": board, "index": 0, "model": "openai/gpt-x"})
    assert wrong.status_code == 422
    assert problem("function Scene(){ fetch('/x') }") and problem("function Scene(){ return Math.random() }")
    assert problem(good) is None
