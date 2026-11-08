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
    made = await client.post("/api/admin/marketing/videos", json={"series_id": str(sid), "format": "16:9"},
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
    video = (await client.post("/api/admin/marketing/videos", json={"series_id": str(sid)},
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
