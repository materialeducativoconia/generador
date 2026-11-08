"""/admin/marketing: DeepSeek writes a promotional video's script from a real tome; the team edits it."""

import json

from tests.db.test_jobs import engine  # noqa: F401 - a fixture
from tests.db.test_me import bearer
from tests.db.test_versions import _written
from tests.fakes import ScriptedLLM

SCRIPT = {"hook": "¿Otro domingo armando material?", "request": "Quiero un cuento sobre Lía y el águila para 6 años",
          "plan": "Jelyx arma el plan", "cover": "Pinta la portada", "pages": "Y cada página, ilustrada",
          "pdf": "Tu PDF, listo para imprimir", "cta": "Pruébalo gratis", "post": "Del tema al libro. #docentes"}


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
    assert "Libro:" in llm.calls[0][-1]["content"]  # the tome's facts reach the scriptwriter

    edited = await client.patch(f"/api/admin/marketing/videos/{video['id']}", headers=bearer(key, admin),
                                json={"format": "9:16", "script": {**SCRIPT, "cta": "Haz tu libro gratis"}})
    assert edited.json()["video"]["script"]["cta"] == "Haz tu libro gratis" and edited.json()["video"]["format"] == "9:16"
    listed = (await client.get("/api/admin/marketing/videos", headers=bearer(key, admin))).json()["videos"]
    assert any(v["id"] == video["id"] for v in listed)
    assert (await client.delete(f"/api/admin/marketing/videos/{video['id']}", headers=bearer(key, admin))).status_code == 204
