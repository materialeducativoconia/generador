"""First adopters: free license links (a plan for some months, handed out by the team), the activity log the team
learns from, and the feedback bubble where DeepSeek talks briefly with the user to write down a problem or an idea
precisely. Everything is read in /admin."""

import json
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from app import credits
from app.agents import AgentFailed, _json_call
from app.api.admin import _staff, assign_plan
from app.api.deps import current_user_id
from app.errors import ApiError
from app.llm import UpstreamAuthError, UpstreamError
from app.plans import PAID, PLANS

log = logging.getLogger("api")
router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
Event = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{1,47}$")]


# ----------------------------------------------------------------------------------------------------- activity

async def log_event(conn, user_id, event: str, props: dict | None = None, path: str | None = None) -> None:
    """One thing a user did, for the team to learn from (never the user's content beyond a short excerpt)."""
    await conn.execute(text(
        "insert into public.activity_events (user_id, event, path, props) values (:u, :e, :p, cast(:x as jsonb))"),
        {"u": user_id, "e": event, "p": path, "x": json.dumps(props or {}, ensure_ascii=False)[:4000]})


async def recent(conn, user_id, event: str, since: timedelta) -> int:
    """How many times a user did something lately: the free AI calls (summary, feedback) are capped with it."""
    return (await conn.execute(text(
        "select count(*) from public.activity_events where user_id = :u and event = :e and created_at > :t"),
        {"u": user_id, "e": event, "t": datetime.now(UTC) - since})).scalar_one()


class Tracked(BaseModel):
    event: Event
    path: str | None = Field(default=None, max_length=200)
    props: dict = Field(default_factory=dict)


class Batch(BaseModel):
    events: list[Tracked] = Field(max_length=30)


@router.post("/api/activity", status_code=204)
async def track(body: Batch, request: Request, user_id: UserId):
    """What the browser saw the user do (pages opened, buttons pressed), sent in batches."""
    async with request.app.state.engine.begin() as conn:
        for e in body.events:
            await log_event(conn, user_id, e.event, e.props, e.path)


@router.get("/api/admin/activity")
async def activity(request: Request, user_id: UserId, user: uuid.UUID | None = None,
                   event: str = Query("", max_length=48), days: int = Query(7, ge=1, le=90)):
    """The latest events (of one user, or one kind), what is done most and how many people used the app each day."""
    since = datetime.now(UTC) - timedelta(days=days)
    where = "e.created_at >= :since" + (" and e.user_id = :user" if user else "") + (" and e.event = :event" if event else "")
    args = {"since": since, "user": user, "event": event}
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        rows = (await conn.execute(text(
            f"""select e.id, e.user_id::text, p.email, p.display_name, e.event, e.path, e.props, e.created_at,
                       exists(select 1 from public.license_redemptions r where r.user_id = e.user_id) as adopter
                  from public.activity_events e left join public.profiles p on p.id = e.user_id
                 where {where} order by e.created_at desc, e.id desc limit 300"""), args)).mappings().all()
        top = (await conn.execute(text(
            f"""select e.event, count(*) as n, count(distinct e.user_id) as users from public.activity_events e
                 where {where} group by 1 order by 2 desc limit 30"""), args)).mappings().all()
        daily = (await conn.execute(text(
            f"""select (e.created_at at time zone 'utc')::date as day, count(distinct e.user_id) as users,
                       count(*) as events
                  from public.activity_events e where {where} group by 1 order by 1"""), args)).mappings().all()
    return {"events": [{**r, "id": r["id"], "props": _json(r["props"]), "created_at": r["created_at"].isoformat()}
                       for r in rows],
            "top": [dict(r) for r in top],
            "daily": [{"day": r["day"].isoformat(), "users": r["users"], "events": r["events"]} for r in daily]}


# ----------------------------------------------------------------------------------------------------- licenses

class NewLicense(BaseModel):
    plan: Literal["docente", "creador", "editorial"] = "docente"
    months: int = Field(default=3, ge=1, le=24)
    max_uses: int = Field(default=1, ge=1, le=1000)
    note: str = Field(default="", max_length=200)  # who it is for: «Escuela Benito Juárez», «grupo de Facebook»
    expires_days: int | None = Field(default=30, ge=1, le=365)  # until when the link opens; None: no end


LICENSE_FIELDS = """l.id::text, l.code, l.plan, l.months, l.max_uses, l.uses, l.note, l.expires_at, l.revoked_at,
                    l.created_at"""


def _license(r) -> dict:
    now = datetime.now(UTC)
    state = ("revocado" if r["revoked_at"] else "vencido" if r["expires_at"] and r["expires_at"] < now
             else "agotado" if r["uses"] >= r["max_uses"] else "activo")
    out = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in dict(r).items()}
    return {**out, "state": state}


@router.post("/api/admin/licenses", status_code=201)
async def new_license(body: NewLicense, request: Request, user_id: UserId):
    code = secrets.token_urlsafe(9)
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        row = (await conn.execute(text(
            f"""insert into public.license_links as l (code, plan, months, max_uses, note, expires_at, created_by)
                values (:c, :p, :m, :n, :note, :e, :u) returning {LICENSE_FIELDS}"""),
            {"c": code, "p": body.plan, "m": body.months, "n": body.max_uses, "note": body.note.strip(), "u": user_id,
             "e": datetime.now(UTC) + timedelta(days=body.expires_days) if body.expires_days else None}
        )).mappings().one()
    return {"license": _license(row)}


@router.get("/api/admin/licenses")
async def licenses(request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        rows = (await conn.execute(text(
            f"select {LICENSE_FIELDS} from public.license_links l order by l.created_at desc limit 200"
        ))).mappings().all()
        users = (await conn.execute(text(
            """select r.link_id::text, r.user_id::text, p.email, p.display_name, r.redeemed_at,
                      (select count(*) from public.series s where s.user_id = r.user_id) as tomes,
                      (select max(e.created_at) from public.activity_events e where e.user_id = r.user_id) as last_seen,
                      (select count(*) from public.feedback f where f.user_id = r.user_id) as feedback
                 from public.license_redemptions r join public.profiles p on p.id = r.user_id
                order by r.redeemed_at desc"""))).mappings().all()
    by_link: dict[str, list] = {}
    for u in users:
        by_link.setdefault(u["link_id"], []).append(
            {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in dict(u).items() if k != "link_id"})
    return {"licenses": [{**_license(r), "users": by_link.get(r["id"], [])} for r in rows]}


@router.post("/api/admin/licenses/{license_id}/revoke")
async def revoke_license(license_id: uuid.UUID, request: Request, user_id: UserId):
    """The link stops opening; whoever already used it keeps the plan until it ends."""
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        row = (await conn.execute(text(
            f"""update public.license_links l set revoked_at = coalesce(revoked_at, now()) where id = :id
                returning {LICENSE_FIELDS}"""), {"id": license_id})).mappings().first()
    if row is None:
        raise ApiError(404, "not_found", "Esa licencia no existe.")
    return {"license": _license(row)}


@router.get("/api/licenses/{code}")
async def license_info(code: str, request: Request):
    """What a link gives, shown before signing in (no account needed to read it)."""
    async with request.app.state.engine.connect() as conn:
        row = (await conn.execute(text(f"select {LICENSE_FIELDS} from public.license_links l where code = :c"),
                                  {"c": code})).mappings().first()
    if row is None:
        raise ApiError(404, "not_found", "Este enlace de licencia no existe.")
    lic = _license(row)
    return {"plan": lic["plan"], "plan_label": PLANS[lic["plan"]].label, "months": lic["months"],
            "credits": PLANS[lic["plan"]].credits, "valid": lic["state"] == "activo", "state": lic["state"]}


@router.post("/api/licenses/{code}/redeem")
async def redeem_license(code: str, request: Request, user_id: UserId):
    """The signed-in user takes the link's plan: one free license per person, never over a better plan."""
    async with request.app.state.engine.begin() as conn:
        email = (await conn.execute(text("select email from public.profiles where id = :u"),
                                    {"u": user_id})).scalar_one_or_none()
        if not email:
            raise ApiError(403, "sign_in_required", "Entra con Google para activar tu licencia.")
        link = (await conn.execute(text(
            f"select {LICENSE_FIELDS} from public.license_links l where code = :c for update"), {"c": code}
        )).mappings().first()
        if link is None:
            raise ApiError(404, "not_found", "Este enlace de licencia no existe.")
        mine = (await conn.execute(text(
            "select link_id::text from public.license_redemptions where user_id = :u"), {"u": user_id})).scalar()
        if mine == link["id"]:
            return {"plan": link["plan"], "already": True}
        if mine:
            raise ApiError(409, "already_redeemed", "Ya activaste una licencia gratis con esta cuenta.")
        state = _license(link)["state"]
        if state != "activo":
            raise ApiError(410, "license_" + {"revocado": "revoked", "vencido": "expired"}.get(state, "used_up"),
                           f"Este enlace de licencia está {state}. Pide uno nuevo al equipo de Jelyx Docs.")
        acc = await credits.account(conn, user_id)
        if acc.plan_key in PAID and PAID.index(acc.plan_key) >= PAID.index(link["plan"]):
            raise ApiError(409, "has_plan", f"Ya tienes el plan {acc.plan.label}: esta licencia no lo mejora.")
        await assign_plan(conn, acc.org_id, link["plan"], link["months"], "gratis de primeros usuarios")
        await conn.execute(text("update public.license_links set uses = uses + 1 where id = cast(:id as uuid)"),
                           {"id": link["id"]})
        await conn.execute(text(
            """insert into public.license_redemptions (link_id, user_id, org_id)
               values (cast(:l as uuid), :u, :o)"""), {"l": link["id"], "u": user_id, "o": acc.org_id})
        await log_event(conn, user_id, "license_redeemed", {"plan": link["plan"], "months": link["months"]})
    return {"plan": link["plan"], "already": False}


# ----------------------------------------------------------------------------------------------------- feedback

FEEDBACK_SYSTEM = """Eres quien recibe la retroalimentación de Jelyx Docs, una app que crea libros y cuadernillos
educativos ilustrados con IA (pedido, esquema, portada, páginas, editor de páginas, PDF y Word). Hablas con un docente
que la está probando gratis como primer usuario.

Tu tarea: entender con precisión UN problema, mejora o idea, en una conversación breve, para que el equipo pueda
actuar. Pregunta solo lo que falta (máximo una pregunta por turno, y no más de 3 en total): qué intentaba hacer, qué
pasó o qué esperaba, en qué parte de la app, y qué tan grave es para su trabajo. Si ya está claro, no preguntes más:
confirma en una frase lo que entendiste y cierra agradeciendo.

Español neutro, tuteo, cálido y breve (1 a 3 frases). Nunca prometas fechas ni funciones. No pidas datos personales.

Responde solo con json:
{"reply": "lo que le dices", "done": true|false,
 "record": null o {"kind": "problema|mejora|idea|elogio", "area": "parte de la app (p. ej. Estudio, Esquema,
  Portada, Editor de páginas, PDF, Planes)", "summary": "una frase clara para el equipo",
  "detail": "lo que pasó, lo que esperaba y el contexto, en 2 a 5 frases", "severity": "baja|media|alta"}}
record va lleno cuando done es true."""

MAX_TURNS = 4  # the user's messages: past these, the conversation is written down as it is


class Record(BaseModel):
    kind: Literal["problema", "mejora", "idea", "elogio"]
    area: str = Field(default="", max_length=80)
    summary: str = Field(min_length=3, max_length=300)
    detail: str = Field(default="", max_length=2000)
    severity: Literal["baja", "media", "alta"] = "media"


class Turn(BaseModel):
    reply: str = Field(min_length=1, max_length=800)
    done: bool = False
    record: Record | None = None


class Line(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class Chat(BaseModel):
    messages: list[Line] = Field(min_length=1, max_length=12)
    path: str | None = Field(default=None, max_length=200)


async def can_give_feedback(conn, user_id) -> bool:
    """The bubble is for the first adopters (who came with a free license) and the team."""
    return bool((await conn.execute(text(
        """select exists(select 1 from public.license_redemptions where user_id = :u)
                  or exists(select 1 from public.profiles where id = :u and platform_role in ('staff', 'admin'))"""),
        {"u": user_id})).scalar())


@router.post("/api/feedback/chat")
async def feedback_chat(body: Chat, request: Request, user_id: UserId):
    """One turn of the feedback conversation; the browser keeps the conversation. When DeepSeek has understood (or
    the user has written enough), it is saved for the team and the answer says so."""
    llm = request.app.state.llm
    async with request.app.state.engine.connect() as conn:
        if not await can_give_feedback(conn, user_id):
            raise ApiError(403, "forbidden", "La retroalimentación está abierta para los primeros usuarios.")
        if await recent(conn, user_id, "feedback_turn", timedelta(hours=1)) >= 30:
            raise ApiError(429, "rate_limited", "Muchos mensajes seguidos: inténtalo en un rato.")
    if body.messages[-1].role != "user":
        raise ApiError(422, "invalid_request", "El último mensaje debe ser tuyo.")
    turns = sum(m.role == "user" for m in body.messages)
    context = f"Pantalla donde abrió la burbuja: {body.path or 'sin indicar'}."
    if turns >= MAX_TURNS:
        context += " Es su último mensaje: cierra ya (done true) y llena record con lo que sabes."
    turn: Turn
    if llm is None:
        turn = _fallback(body.messages)
    else:
        try:
            turn = (await _json_call(llm, [{"role": "system", "content": FEEDBACK_SYSTEM + "\n\n" + context},
                                           *[m.model_dump() for m in body.messages]],
                                     Turn, temperature=0.4, max_tokens=900)).value
        except (AgentFailed, UpstreamError, UpstreamAuthError, ValidationError) as exc:
            log.warning("feedback chat failed: %s", exc)
            turn = _fallback(body.messages)
        if turns >= MAX_TURNS and not (turn.done and turn.record):
            turn = Turn(reply=turn.reply if turn.done else "¡Gracias! Ya lo anoté para el equipo.", done=True,
                        record=turn.record or _fallback(body.messages).record)
    saved = None
    async with request.app.state.engine.begin() as conn:
        await log_event(conn, user_id, "feedback_turn", {"turn": turns}, body.path)
        if turn.done and turn.record:
            transcript = [*[m.model_dump() for m in body.messages], {"role": "assistant", "content": turn.reply}]
            saved = (await conn.execute(text(
                """insert into public.feedback (user_id, kind, area, summary, detail, severity, path, transcript)
                   values (:u, :k, :a, :s, :d, :sev, :p, cast(:t as jsonb)) returning id::text"""),
                {"u": user_id, "k": turn.record.kind, "a": turn.record.area, "s": turn.record.summary,
                 "d": turn.record.detail, "sev": turn.record.severity, "p": body.path,
                 "t": json.dumps(transcript, ensure_ascii=False)})).scalar_one()
            await log_event(conn, user_id, "feedback_sent", {"kind": turn.record.kind, "id": saved}, body.path)
    return {"reply": turn.reply, "done": turn.done and saved is not None, "id": saved}


def _fallback(messages: list[Line]) -> Turn:
    """Without DeepSeek the user's words are kept as they are, so nothing they said is lost."""
    said = " ".join(m.content for m in messages if m.role == "user")
    return Turn(reply="¡Gracias! Lo anoté tal cual para el equipo.", done=True,
                record=Record(kind="mejora", summary=said[:200] if len(said) >= 3 else "Sin detalle", detail=said[:2000]))


@router.get("/api/admin/feedback")
async def feedback_list(request: Request, user_id: UserId, status: str = Query("", max_length=20)):
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        rows = (await conn.execute(text(
            f"""select f.id::text, f.user_id::text, p.email, p.display_name, f.kind, f.area, f.summary, f.detail,
                       f.severity, f.path, f.transcript, f.status, f.created_at
                  from public.feedback f left join public.profiles p on p.id = f.user_id
                 {"where f.status = :st" if status else ""}
                 order by (f.status = 'nuevo') desc, f.created_at desc limit 300"""), {"st": status})).mappings().all()
        counts = dict((await conn.execute(text(
            "select status, count(*) from public.feedback group by 1"))).all())
    return {"feedback": [{**r, "transcript": _json(r["transcript"]), "created_at": r["created_at"].isoformat()}
                         for r in rows], "counts": counts}


class FeedbackEdit(BaseModel):
    status: Literal["nuevo", "visto", "resuelto", "descartado"]


@router.patch("/api/admin/feedback/{feedback_id}")
async def feedback_edit(feedback_id: uuid.UUID, body: FeedbackEdit, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id)
        done = (await conn.execute(text("update public.feedback set status = :s where id = :id returning id"),
                                   {"s": body.status, "id": feedback_id})).first()
    if done is None:
        raise ApiError(404, "not_found", "Esa retroalimentación no existe.")
    return {"status": body.status}


def _json(value):
    return json.loads(value) if isinstance(value, str) else value
