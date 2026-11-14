"""First adopters: free license links, the activity log, the feedback bubble and the order summary before a tome."""

import json

from tests.db.test_me import bearer
from tests.fakes import ScriptedLLM


async def _admin(raw_db, google_user, email):
    admin = await google_user(email=email)
    await raw_db.execute("update public.profiles set platform_role = 'admin' where id = $1", admin)
    return admin


async def test_a_free_license_link_gives_the_teacher_plan_once_per_person_until_it_runs_out(raw_db, google_user, client,
                                                                                           key):
    admin = await _admin(raw_db, google_user, "licencias@jelyx.test")
    teacher = await google_user(plan=None, credits=0)
    other = await google_user(plan=None, credits=0)
    visitor = await google_user(plan=None, credits=0, anonymous=True)

    assert (await client.post("/api/admin/licenses", json={}, headers=bearer(key, teacher))).status_code == 403
    made = await client.post("/api/admin/licenses", headers=bearer(key, admin),
                             json={"months": 2, "max_uses": 1, "note": "Escuela Benito Juárez"})
    assert made.status_code == 201
    lic = made.json()["license"]
    assert lic["plan"] == "docente" and lic["state"] == "activo" and len(lic["code"]) >= 10

    info = (await client.get(f"/api/licenses/{lic['code']}")).json()  # read before signing in
    assert info == {"plan": "docente", "plan_label": "Docente", "months": 2, "credits": 150, "valid": True,
                    "state": "activo"}
    assert (await client.post(f"/api/licenses/{lic['code']}/redeem", headers=bearer(key, visitor))).status_code == 403

    got = await client.post(f"/api/licenses/{lic['code']}/redeem", headers=bearer(key, teacher))
    assert got.json() == {"plan": "docente", "already": False}
    me = (await client.get("/api/me", headers=bearer(key, teacher))).json()
    assert me["plan"]["key"] == "docente" and me["credits"] == 300  # two months of credits
    assert me["first_adopter"] is True and me["feedback"] is True
    again = await client.post(f"/api/licenses/{lic['code']}/redeem", headers=bearer(key, teacher))
    assert again.json()["already"] is True and (await client.get("/api/me", headers=bearer(key, teacher))).json()["credits"] == 300

    used_up = await client.post(f"/api/licenses/{lic['code']}/redeem", headers=bearer(key, other))
    assert used_up.status_code == 410 and used_up.json()["error"]["code"] == "license_used_up"

    second = (await client.post("/api/admin/licenses", headers=bearer(key, admin), json={"max_uses": 5})).json()["license"]
    once = await client.post(f"/api/licenses/{second['code']}/redeem", headers=bearer(key, teacher))
    assert once.json()["error"]["code"] == "already_redeemed"  # one free license per person
    await client.post(f"/api/admin/licenses/{second['id']}/revoke", headers=bearer(key, admin))
    revoked = await client.post(f"/api/licenses/{second['code']}/redeem", headers=bearer(key, other))
    assert revoked.status_code == 410 and revoked.json()["error"]["code"] == "license_revoked"

    listed = (await client.get("/api/admin/licenses", headers=bearer(key, admin))).json()["licenses"]
    first = next(x for x in listed if x["id"] == lic["id"])
    assert first["state"] == "agotado" and [u["user_id"] for u in first["users"]] == [str(teacher)]


async def test_a_license_never_replaces_a_better_plan(raw_db, google_user, client, key):
    admin = await _admin(raw_db, google_user, "licencias-plan@jelyx.test")
    publisher = await google_user(plan="editorial")
    code = (await client.post("/api/admin/licenses", headers=bearer(key, admin), json={})).json()["license"]["code"]

    refused = await client.post(f"/api/licenses/{code}/redeem", headers=bearer(key, publisher))

    assert refused.status_code == 409 and refused.json()["error"]["code"] == "has_plan"


async def test_what_users_do_is_logged_and_the_team_reads_it(raw_db, google_user, client, key):
    admin = await _admin(raw_db, google_user, "actividad@jelyx.test")
    teacher = await google_user()

    sent = await client.post("/api/activity", headers=bearer(key, teacher), json={"events": [
        {"event": "page_view", "path": "/app"}, {"event": "studio.summary_open", "props": {"pages": 8}}]})
    assert sent.status_code == 204
    assert (await client.post("/api/activity", headers=bearer(key, teacher),
                              json={"events": [{"event": "Bad Event!"}]})).status_code == 422
    assert (await client.get("/api/admin/activity", headers=bearer(key, teacher))).status_code == 403

    seen = (await client.get(f"/api/admin/activity?user={teacher}", headers=bearer(key, admin))).json()
    assert [e["event"] for e in seen["events"]] == ["studio.summary_open", "page_view"]
    assert seen["events"][0]["props"] == {"pages": 8} and seen["daily"][-1]["users"] == 1
    assert {t["event"] for t in seen["top"]} == {"page_view", "studio.summary_open"}


async def test_the_feedback_bubble_talks_briefly_and_writes_down_the_problem_for_the_team(raw_db, google_user, client,
                                                                                         key):
    admin = await _admin(raw_db, google_user, "opiniones@jelyx.test")
    stranger = await google_user()
    teacher = await google_user(plan=None, credits=0)
    code = (await client.post("/api/admin/licenses", headers=bearer(key, admin), json={})).json()["license"]["code"]
    await client.post(f"/api/licenses/{code}/redeem", headers=bearer(key, teacher))
    record = {"kind": "problema", "area": "PDF", "summary": "El PDF corta la última línea de las fichas",
              "detail": "Al descargar el cuadernillo de sumas, la última línea de cada ficha sale cortada.",
              "severity": "alta"}
    llm = ScriptedLLM(json.dumps({"reply": "¿En qué tomo te pasó?", "done": False, "record": None}),
                      json.dumps({"reply": "Entendido: el PDF corta la última línea. ¡Gracias!", "done": True,
                                  "record": record}))
    client._transport.app.state.llm = llm
    said = [{"role": "user", "content": "El PDF sale cortado"}]

    assert (await client.post("/api/feedback/chat", headers=bearer(key, stranger),
                              json={"messages": said})).status_code == 403
    first = (await client.post("/api/feedback/chat", headers=bearer(key, teacher),
                               json={"messages": said, "path": "/app/tomos/x"})).json()
    assert first == {"reply": "¿En qué tomo te pasó?", "done": False, "id": None}
    said += [{"role": "assistant", "content": first["reply"]}, {"role": "user", "content": "En el de sumas, al imprimir"}]
    second = (await client.post("/api/feedback/chat", headers=bearer(key, teacher),
                                json={"messages": said, "path": "/app/tomos/x"})).json()
    assert second["done"] is True and second["id"]
    assert "Pantalla donde abrió la burbuja: /app/tomos/x" in llm.calls[0][0]["content"]

    listed = (await client.get("/api/admin/feedback", headers=bearer(key, admin))).json()
    item = next(f for f in listed["feedback"] if f["id"] == second["id"])
    assert item["summary"] == record["summary"] and item["severity"] == "alta" and item["status"] == "nuevo"
    assert [m["role"] for m in item["transcript"]] == ["user", "assistant", "user", "assistant"]
    assert (await client.patch(f"/api/admin/feedback/{item['id']}", headers=bearer(key, admin),
                               json={"status": "resuelto"})).json() == {"status": "resuelto"}


async def test_the_feedback_is_written_down_by_the_fourth_message_whatever_the_model_does(raw_db, google_user, client,
                                                                                         key):
    teacher = await _admin(raw_db, google_user, "opiniones-tope@jelyx.test")  # the team may use the bubble too
    client._transport.app.state.llm = ScriptedLLM(json.dumps({"reply": "¿Algo más?", "done": False, "record": None}))
    said = []
    for i in range(4):
        said += [{"role": "user", "content": f"Detalle {i}"}, {"role": "assistant", "content": "¿Algo más?"}]
    out = (await client.post("/api/feedback/chat", headers=bearer(key, teacher), json={"messages": said[:-1]})).json()

    assert out["done"] is True and out["id"]


async def test_the_order_summary_shows_what_will_be_made_and_charges_nothing(raw_db, google_user, client, key):
    teacher = await google_user(plan="docente", credits=150)
    summary = {"title": "Sumas con frutas", "kind": "Cuadernillo de fichas", "audience": "Niños (5 años)",
               "sections": [{"title": "Contar", "pages": 5}, {"title": "Sumar", "pages": 5}],  # 10, but 8 were asked
               "includes": ["Fichas ilustradas", "Solucionario"], "notes": ["¿Sumas hasta 5 o hasta 10?"]}
    client._transport.app.state.llm = ScriptedLLM(json.dumps(summary))
    order = {"request": "Fichas de sumas con frutas para niños de 5 años", "page_count": 8, "format": "worksheets"}

    got = (await client.post("/api/series/summary", headers=bearer(key, teacher), json=order)).json()

    assert got["ai"] is True and got["credits"] == 13 and got["now"] == 5 and got["balance"] == 150
    assert [p["pages"] for p in got["summary"]["sections"]] == [4, 4]  # the split always adds up to the pages chosen
    assert got["summary"]["notes"] == ["¿Sumas hasta 5 o hasta 10?"]
    me = (await client.get("/api/me", headers=bearer(key, teacher))).json()
    assert me["credits"] == 150  # nothing created, nothing charged
    assert await raw_db.fetchval("select count(*) from public.series where user_id = $1", teacher) == 0
    assert await raw_db.fetchval("select count(*) from public.activity_events where user_id = $1 and event = 'tome_summary'",
                                 teacher) == 1

    client._transport.app.state.llm = ScriptedLLM()  # DeepSeek down: the request is said back as it was asked
    plain = (await client.post("/api/series/summary", headers=bearer(key, teacher), json=order)).json()
    assert plain["ai"] is False and plain["summary"]["sections"] == [{"title": "Contenido", "pages": 8}]
