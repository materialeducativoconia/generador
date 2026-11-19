"""/admin/marketing: promotional videos. DeepSeek writes a template's script from a real tome; the admin edits it,
previews the video and renders the MP4 in the browser."""

import asyncio
import hashlib
import json
import logging
import re
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from app.agents import AgentFailed
from app.coder import BOARD_SYSTEM, CHANGE, PROMPT_WRITER, SYSTEM, USER, fill, json_of, label
from app.api.admin import _staff
from app.api.deps import current_user_id
from app.errors import ApiError
from app.llm import UpstreamAuthError, UpstreamError
from app.marketing import (MUSIC, SCENE_LIST, STRUCTURES, Scene, Storyboard, VideoScript, director, pick_music, pick_structure, script_director,
                           tidy_storyboard, video_script)
from app.render import GENRE_LABEL
from app.voice import seconds

log = logging.getLogger("api")
router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
FIELDS = "id::text, template, series_id::text, format, script, created_at, updated_at, mp4_key, rendered_at"
BUCKET = "marketing"
Format = Literal["9:16", "1:1", "16:9"]


def _out(row) -> dict:
    video = dict(row)
    if isinstance(video["script"], str):
        video["script"] = json.loads(video["script"])
    video["has_mp4"] = bool(video.pop("mp4_key"))
    return video


@router.get("/api/admin/marketing/videos")
async def list_videos(request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        rows = (await conn.execute(text(
            f"select {FIELDS} from public.marketing_videos order by created_at desc limit 100"))).mappings().all()
    return {"videos": [_out(r) for r in rows]}


class NewVideo(BaseModel):
    series_id: uuid.UUID
    format: Format = "9:16"
    # The director (any video asked for in words) or the first fixed template, «De un tema a un libro en 30 s».
    template: Literal["storyboard", "topic_to_book"] = "storyboard"
    ask: str | None = Field(default=None, max_length=500)  # what video the team needs (for the fixed one: its angle)
    kind: Literal["marketing", "explainer", "tutorial", "motion"] = "marketing"
    duration: Literal[15, 30, 45, 60] = 30
    structure: str = "auto"  # a key of STRUCTURES, or the director picks one the last video did not use
    script: dict | None = None  # a storyboard already proposed and reviewed: saved as it is, without asking again
    script_text: str | None = Field(default=None, max_length=4000)  # «Desde mi guion»: the team's own words
    music: str = "auto"  # a key of MUSIC, «auto» (the kind's) or «none»
    claude_prompt: str | None = Field(default=None, max_length=8000)  # «Pegar prompt para Claude»: Claude directs it
    model: str = ""  # the Claude model of the prompt modes; empty: the first configured


async def _context(request: Request, user_id: uuid.UUID, series_id: uuid.UUID):
    """The tome a video shows, the last storyboards and the real screenshots; 404 for a tome that does not exist."""
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        series = (await conn.execute(text(
            """select coalesce(title, topic) as title, topic, genre::text as genre,
                      coalesce(audience->>'label', '') as audience,
                      array(select l.title from public.lessons l where l.series_id = s.id order by l.position) as sections,
                      (select concat_ws(' | ', b->>'question', b->>'answer', b->'notes'->>0)
                         from public.lessons l, jsonb_array_elements(l.content_json->'blocks') b
                        where l.series_id = s.id and b->>'size' = 'plate' and b ? 'question'
                        order by l.position limit 1) as sample,
                      (select string_agg(c->>'name', ', ') from jsonb_array_elements(
                          case when jsonb_typeof(s."cast") = 'array' then s."cast" else '[]'::jsonb end) c) as cast_names
                 from public.series s where id = :s"""), {"s": series_id})).mappings().first()
        # The last storyboards, so the next one is told another way.
        recent = (await conn.execute(text(
            """select script->>'title' as title, script->>'structure' as structure, script->>'kind' as kind,
                      array(select e->>'type' from jsonb_array_elements(script->'scenes') e) as scenes
                 from public.marketing_videos where template = 'storyboard'
                order by created_at desc limit 6"""))).mappings().all()
        captures = [dict(id=r["id"], name=r["name"], description=r["description"],
                         focus=[(f.get("label") or "") for f in (json.loads(r["focus"]) if isinstance(r["focus"], str) else r["focus"])])
                    for r in (await conn.execute(text(
                        "select id::text, name, description, focus from public.marketing_captures order by created_at"
                    ))).mappings().all()]
    if series is None:
        raise ApiError(404, "not_found", "Ese tomo no existe.")
    return series, recent, captures


async def _write(request: Request, user_id: uuid.UUID, body: NewVideo) -> Storyboard | VideoScript:
    """DeepSeek (or Claude, from a prompt) directs the video of a tome; nothing is saved."""
    if body.template == "storyboard" and (body.claude_prompt or "").strip():
        return await _claude_board(request, user_id, body)
    llm = request.app.state.llm
    if llm is None:
        raise ApiError(503, "unavailable", "El guionista no está configurado.")
    if body.structure != "auto" and body.structure not in STRUCTURES:
        raise ApiError(422, "invalid_request", "Esa estructura no existe.")
    series, recent, captures = await _context(request, user_id, body.series_id)
    book = dict(title=series["title"], topic=series["topic"], audience=series["audience"], sections=list(series["sections"]))
    book_kind = GENRE_LABEL.get(series["genre"] or "", "Libro")
    try:
        music = pick_music(body.music, body.kind)
        if body.template == "storyboard" and (body.script_text or "").strip():
            try:
                result = await script_director(llm, script=body.script_text, kind=body.kind, book_kind=book_kind,
                                               cast=series["cast_names"], captures=captures, music=music, **book)
            except ValueError as exc:
                raise ApiError(422, "invalid_request", str(exc)) from exc
        elif body.template == "storyboard":
            last = next((r["structure"] for r in recent if r["kind"] == body.kind), None)
            structure = pick_structure(body.kind, last) if body.structure == "auto" else body.structure
            result = await director(llm, ask=(body.ask or "").strip() or "Un video que muestre cómo funciona la app",
                                    kind=body.kind, duration=body.duration, book_kind=book_kind,
                                    sample=series["sample"], structure=structure, cast=series["cast_names"],
                                    recent=[dict(title=r["title"], scenes=list(r["scenes"])) for r in recent],
                                    captures=captures, **book)
            result.value.music = music
            result.value = tidy_storyboard(result.value)
        else:
            result = await video_script(llm, kind=book_kind, angle=body.ask, **book)
    except AgentFailed as exc:
        log.warning("video script failed: %s", [(a.outcome, (a.error or "")[:300]) for a in exc.attempts])
        raise ApiError(502, "upstream_error", "DeepSeek no pudo escribir el guion; inténtalo de nuevo.") from exc
    return result.value


def _coder_model(request: Request, model: str):
    coder = request.app.state.coder
    if coder is None or not coder.models:
        raise ApiError(503, "unavailable", "Claude no está configurado (OPENROUTER_API_KEY).")
    model = model or coder.models[0]
    if model not in coder.models:
        raise ApiError(422, "invalid_request", "Ese modelo no está disponible.")
    return coder, model


def _book_facts(series, captures) -> str:
    facts = (f"Libro que se muestra: {series['title']} ({GENRE_LABEL.get(series['genre'] or '', 'Libro')})\n"
             f"Tema: {series['topic']}\nPara: {series['audience'] or 'sin indicar'}\n"
             f"Secciones: {'; '.join(list(series['sections'])[:8]) or 'sin secciones'}\n"
             + (f"Personajes: {series['cast_names']}\n" if series["cast_names"] else "Sin personajes fijos.\n")
             + (f"Una página de ejemplo: {series['sample']}\n" if series["sample"] else ""))
    if captures:
        facts += ("Capturas reales de la app para type screen (id: qué muestra):\n"
                  + "\n".join(f"- {c['id']}: {c['name']} {c['description'] or ''}".rstrip() for c in captures) + "\n")
    return facts


async def _claude(coder, model: str, messages: list[dict], max_tokens: int) -> tuple[str, float]:
    try:
        return await coder.ask(model, messages, max_tokens)
    except UpstreamAuthError as exc:
        raise ApiError(503, "unavailable", "OpenRouter rechazó la clave o no tiene saldo.") from exc
    except UpstreamError as exc:
        log.warning("claude failed: %s", exc)
        raise ApiError(502, "upstream_error", f"{exc} Inténtalo de nuevo.") from exc


class PromptAsk(BaseModel):
    series_id: uuid.UUID
    ask: str = Field(default="", max_length=500)
    kind: Literal["marketing", "explainer", "tutorial", "motion"] = "motion"
    format: Format = "9:16"
    duration: Literal[15, 30, 45, 60] = 30
    model: str = ""


@router.post("/api/admin/marketing/claude-prompt")
async def claude_prompt(body: PromptAsk, request: Request, user_id: UserId):
    """«Generar prompt para Claude»: the full brief of a motion-graphics video, to paste here or in Claude Code."""
    coder, model = _coder_model(request, body.model)
    series, _, captures = await _context(request, user_id, body.series_id)
    width, height = SIZES[body.format]
    system = fill(PROMPT_WRITER, format=body.format, width=width, height=height, duration=body.duration,
                  colors="fondo #08071a o #ffffff, texto #ffffff o #0c0a09, acento #5b4cf0 / #8f7dff, cálido #ffd166")
    user = (f"Tipo de video: {body.kind}\nIdea del equipo: {body.ask.strip() or 'muestra lo que hace la app con este libro'}\n"
            + _book_facts(series, captures))
    prompt, cost = await _claude(coder, model, [{"role": "system", "content": system}, {"role": "user", "content": user}], 4000)
    return {"prompt": prompt.strip()[:8000], "model": model, "cost": cost}


# Scenes drawn from the real tome or app (its cover, pages, characters, screenshots): never replaced by code.
REAL_SCENES = {"cover", "pages", "pdf", "plan", "characters", "formats", "screen", "compose", "editor_open", "editor_move",
               "editor_facts", "editor_repaint", "editor_cover", "editor_save"}


async def _claude_board(request: Request, user_id: uuid.UUID, body: NewVideo) -> Storyboard:
    """«Pegar prompt para Claude»: Claude reads the team's prompt and directs the storyboard; the scenes it marks are
    then programmed a medida (request.state.tailor says which)."""
    coder, model = _coder_model(request, body.model)
    series, _, captures = await _context(request, user_id, body.series_id)
    known = {c["id"]: len(c["focus"]) for c in captures}
    system = BOARD_SYSTEM.replace("{scenes}", SCENE_LIST).replace("{duration}", str(body.duration))
    user = _book_facts(series, captures) + f"\nFormato: {body.format}\n\nPrompt del equipo:\n{body.claude_prompt.strip()}"
    reply, _ = await _claude(coder, model, [{"role": "system", "content": system}, {"role": "user", "content": user}], 6000)
    data = json_of(reply)
    raw = data.get("scenes") if isinstance(data.get("scenes"), list) else []
    scenes, tailor = [], []
    for sc in raw[:24]:
        if not isinstance(sc, dict):
            continue
        sc = dict(sc)
        wants = bool(sc.pop("tailor", False))
        if sc.get("type") == "screen" and sc.get("capture") not in known:
            sc["type"], wants = "motion", True
        try:
            scene = Scene.model_validate({**sc, "seconds": min(12, max(1.5, float(sc.get("seconds") or 4)))})
        except (ValidationError, TypeError, ValueError):
            scene, wants = Scene(type="motion", caption=str(sc.get("caption") or "")[:70], voice=str(sc.get("voice") or "")[:300]), True
        if wants and scene.type != "cta" and scene.type not in REAL_SCENES:
            tailor.append(len(scenes))
        scenes.append(scene)
    if not scenes:
        raise ApiError(502, "upstream_error", "Claude no devolvió escenas; inténtalo de nuevo.")
    try:
        board = Storyboard.model_validate({"kind": body.kind, "duration": body.duration, "source": "ask", "structure": "claude",
                                           "look": data.get("look") if data.get("look") in LOOK_COLORS else "noche",
                                           "title": str(data.get("title") or series["title"])[:80], "post": str(data.get("post") or ""),
                                           "music": pick_music(body.music, body.kind), "scenes": [sc.model_dump() for sc in scenes]})
    except ValidationError as exc:
        raise ApiError(502, "upstream_error", "Claude devolvió un storyboard incompleto; inténtalo de nuevo.") from exc
    marked = [board.scenes[i] for i in tailor]
    board = tidy_storyboard(board)  # may open on a title or drop a call to action in the middle: found by identity
    request.state.tailor = [i for i, sc in enumerate(board.scenes) if any(sc is m for m in marked)]
    return board


@router.get("/api/admin/marketing/structures")
async def structures(request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
    return {"structures": [dict(key=k, label=label, kinds=list(kinds), how=how)
                           for k, (label, kinds, how) in STRUCTURES.items()],
            "music": [dict(key=k, title=title, mood=mood, bpm=bpm) for k, (title, mood, bpm, _) in MUSIC.items()],
            "coders": [dict(key=m, label=label(m)) for m in (request.app.state.coder.models if request.app.state.coder else [])]}


@router.post("/api/admin/marketing/storyboard")
async def propose(body: NewVideo, request: Request, user_id: UserId):
    """A storyboard to look at, change or ask again before the video exists."""
    script = await _write(request, user_id, body.model_copy(update={"template": "storyboard"}))
    return {"script": script.model_dump(), "tailor": getattr(request.state, "tailor", [])}


@router.post("/api/admin/marketing/videos", status_code=201)
async def new_video(body: NewVideo, request: Request, user_id: UserId):
    if body.template == "storyboard" and body.script is not None:
        try:
            script = tidy_storyboard(Storyboard.model_validate(body.script))
        except ValidationError as exc:
            raise ApiError(422, "validation_error", "Revisa el guion.", {"errors": exc.errors()}) from exc
        async with request.app.state.engine.connect() as conn:
            await _staff(conn, user_id)
    else:
        script = await _write(request, user_id, body)
    async with request.app.state.engine.begin() as conn:
        row = (await conn.execute(text(
            f"""insert into public.marketing_videos (series_id, template, format, script, created_by)
                values (:s, :t, :f, cast(:sc as jsonb), :u) returning {FIELDS}"""),
            {"s": body.series_id, "t": body.template, "f": body.format, "sc": script.model_dump_json(),
             "u": user_id})).mappings().one()
    return {"video": _out(row)}


SIZES = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
FPS = 30
ICON_NAMES = ("sparkle, book, pencil, clock, star, heart, check, palette, download, people, idea, rocket, puzzle, globe, "
              "apple, music, leaf, calculator, school, printer")
LOOK_COLORS = {"claro": ("#ffffff", "#0c0a09", "#5b4cf0"), "oscuro": ("#0c0a09", "#ffffff", "#a99cff"),
               "color": ("#5b4cf0", "#ffffff", "#ffd166"), "noche": ("#08071a", "#ffffff", "#8f7dff")}


class SceneAsk(BaseModel):
    board: dict  # the storyboard as it is now (a draft or a saved video's)
    index: int = Field(ge=0, lt=24)  # the scene to program
    format: Format = "9:16"
    book: str = Field(default="", max_length=200)
    model: str = ""  # one of the configured Claude models; empty: the first
    change: str | None = Field(default=None, max_length=400)  # «hazla más dinámica»: rewrites the scene's current code


@router.post("/api/admin/marketing/scene-code")
async def scene_code(body: SceneAsk, request: Request, user_id: UserId):
    """«Escena a medida»: Claude programs one scene as a Remotion component; nothing is saved (the board keeps it)."""
    coder, model = _coder_model(request, body.model)
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
    try:
        board = Storyboard.model_validate(body.board)
    except ValidationError as exc:
        raise ApiError(422, "validation_error", "Revisa el guion.", {"errors": exc.errors()}) from exc
    if body.index >= len(board.scenes):
        raise ApiError(422, "invalid_request", "Esa escena no existe.")
    scene = board.scenes[body.index]
    width, height = SIZES[body.format]
    bg, ink, accent = LOOK_COLORS[board.look]
    outline = "\n".join(f"{'▶' if i == body.index else ' '} {i + 1}. {s.type} · {s.seconds:g} s · «{s.caption or s.voice[:60]}»"
                         for i, s in enumerate(board.scenes))
    extra = (f"Dato extra (text): «{scene.text}»" if scene.text else "") + (
        "\nEs la última escena: cierra con «docs.jelyx.app» bien visible." if body.index == len(board.scenes) - 1 else "")
    messages = [
        {"role": "system", "content": fill(SYSTEM, fps=FPS, width=width, height=height, icons=ICON_NAMES, max=12000)},
        {"role": "user", "content": fill(USER, title=board.title, book=body.book or board.title, bg=bg, ink=ink, accent=accent,
                                         outline=outline, seconds=f"{scene.seconds:g}", dur=round(scene.seconds * FPS),
                                         caption=scene.caption, voice=scene.voice, extra=extra)},
    ]
    if body.change and scene.code:
        messages.append({"role": "user", "content": fill(CHANGE, code=scene.code, change=body.change.strip())})
    elif body.change:
        messages[-1]["content"] += f"\nIndicación del equipo: {body.change.strip()}"
    try:
        code, cost = await coder.write(model, messages)
    except UpstreamAuthError as exc:
        raise ApiError(503, "unavailable", "OpenRouter rechazó la clave o no tiene saldo.") from exc
    except UpstreamError as exc:
        log.warning("scene code failed: %s", exc)
        raise ApiError(502, "upstream_error", f"{exc} Inténtalo de nuevo.") from exc
    return {"code": code, "model": model, "cost": cost}


class VideoEdit(BaseModel):
    format: Format | None = None
    script: dict | None = None  # a VideoScript or a Storyboard, by the video's template


@router.patch("/api/admin/marketing/videos/{video_id}")
async def edit_video(video_id: uuid.UUID, body: VideoEdit, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id)
        script = None
        if body.script is not None:
            template = (await _video(conn, video_id))["template"]
            try:
                script = (tidy_storyboard(Storyboard.model_validate(body.script)) if template == "storyboard"
                          else VideoScript.model_validate(body.script)).model_dump_json()
            except ValidationError as exc:
                raise ApiError(422, "validation_error", "Revisa el guion.", {"errors": exc.errors()}) from exc
        row = (await conn.execute(text(
            f"""update public.marketing_videos set format = coalesce(:f, format),
                       script = coalesce(cast(:sc as jsonb), script), updated_at = now(),
                       -- the kept MP4 shows the old words or size: it is made again
                       mp4_key = case when coalesce(:f, format) = format and (cast(:sc as jsonb) is null
                                       or cast(:sc as jsonb) = script) then mp4_key end
                 where id = :id returning {FIELDS}"""),
            {"id": video_id, "f": body.format, "sc": script}
        )).mappings().first()
    if row is None:
        raise ApiError(404, "not_found", "Ese video no existe.")
    return {"video": _out(row)}


@router.delete("/api/admin/marketing/videos/{video_id}", status_code=204)
async def delete_video(video_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id)
        await conn.execute(text("delete from public.marketing_videos where id = :id"), {"id": video_id})


async def _video(conn, video_id) -> dict:
    row = (await conn.execute(text(f"select {FIELDS} from public.marketing_videos where id = :id"),
                              {"id": video_id})).mappings().first()
    if row is None:
        raise ApiError(404, "not_found", "Ese video no existe.")
    return dict(row)


@router.post("/api/admin/marketing/videos/{video_id}/upload")
async def mp4_upload(video_id: uuid.UUID, request: Request, user_id: UserId):
    """Where the browser puts the MP4 it just rendered (straight to storage, never through this server)."""
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        await _video(conn, video_id)
    key = f"{video_id}/{uuid.uuid4().hex[:8]}.mp4"
    return {"key": key, "upload_url": await request.app.state.storage.upload_url(key, bucket=BUCKET)}


class Rendered(BaseModel):
    key: str = Field(pattern=r"^[0-9a-f-]{36}/[0-9a-f]{8}\.mp4$")


@router.post("/api/admin/marketing/videos/{video_id}/rendered")
async def mp4_rendered(video_id: uuid.UUID, body: Rendered, request: Request, user_id: UserId):
    """The MP4 is up: the video keeps it until its script or format changes."""
    if not body.key.startswith(f"{video_id}/"):
        raise ApiError(422, "invalid_request", "Ese archivo no es de este video.")
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id)
        row = (await conn.execute(text(
            f"""update public.marketing_videos set mp4_key = :k, rendered_at = now() where id = :id
                returning {FIELDS}"""), {"id": video_id, "k": body.key})).mappings().first()
    if row is None:
        raise ApiError(404, "not_found", "Ese video no existe.")
    return {"video": _out(row)}


@router.get("/api/admin/marketing/videos/{video_id}/mp4")
async def mp4_download(video_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        video = await _video(conn, video_id)
    if not video["mp4_key"]:
        raise ApiError(404, "not_found", "Este video aún no tiene MP4: créalo con «Crear MP4».")
    name = f"jelyx-{video['format'].replace(':', 'x')}-{str(video_id)[:6]}.mp4"
    return {"url": await request.app.state.storage.signed_url(video["mp4_key"], expires_in=300, download_name=name,
                                                              bucket=BUCKET)}


@router.post("/api/admin/marketing/videos/{video_id}/voice")
async def voice(video_id: uuid.UUID, request: Request, user_id: UserId):
    """The voiceover read by Gemini TTS (OpenRouter): one clip per scene of a storyboard, or the fixed template's
    whole voiceover. Each clip is kept under the hash of its words, so a line that did not change is not paid again."""
    tts, storage = request.app.state.voice, request.app.state.storage
    if tts is None or storage is None:
        raise ApiError(503, "unavailable", "La voz no está configurada.")
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        video = await _video(conn, video_id)
    script = json.loads(video["script"]) if isinstance(video["script"], str) else video["script"]
    if video["template"] == "storyboard":
        lines = [(i, (sc.get("voice") or "").strip()) for i, sc in enumerate(script.get("scenes", []))]
    else:
        lines = [(-1, (script.get("voiceover") or "").strip())]
    lines = [(i, t) for i, t in lines if t]
    keys = {i: f"{video_id}/voice/{hashlib.sha1(f'{tts.model}|{tts.voice}|{t}'.encode()).hexdigest()[:16]}.wav"
            for i, t in lines}
    kept = await storage.signed_urls(list(keys.values()), bucket=BUCKET)

    async def clip(i: int, words: str) -> dict:
        key = keys[i]
        if key not in kept:
            try:
                audio = await tts.speak(said(words))
            except (UpstreamError, UpstreamAuthError) as exc:
                log.warning("voice failed: %s", exc)
                raise ApiError(502, "upstream_error", "OpenRouter no pudo leer la voz; inténtalo de nuevo.") from exc
            await storage.upload(key, audio, content_type="audio/wav", bucket=BUCKET)
            kept.update(await storage.signed_urls([key], bucket=BUCKET))
            return dict(scene=i, url=kept[key], seconds=round(seconds(audio), 2))
        return dict(scene=i, url=kept[key], seconds=None)

    clips = await asyncio.gather(*(clip(i, t) for i, t in lines))
    return {"clips": list(clips)}


def said(words: str) -> str:
    """The line as the voice should read it: the address spelled out, as a script may write it plainly."""
    return re.sub(r"(https?://)?docs\.jelyx\.app/?", "docs punto jelyx punto app", words, flags=re.I)


# Real screenshots of the app: uploaded once, each with the points the camera zooms to.
CAPTURE_FIELDS = "id::text, name, description, image_key, width, height, focus, created_at"


class Point(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    label: str = Field(default="", max_length=60)


class NewCapture(BaseModel):
    key: str = Field(pattern=r"^captures/[0-9a-f]{12}\.(png|jpg|webp)$")
    name: str = Field(min_length=1, max_length=80)
    width: int = Field(gt=0, le=8000)
    height: int = Field(gt=0, le=8000)


class CaptureEdit(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    focus: list[Point] | None = Field(default=None, max_length=12)


async def _captures_out(request: Request, rows) -> list[dict]:
    urls = await request.app.state.storage.signed_urls([r["image_key"] for r in rows], bucket=BUCKET, expires_in=6 * 3600)
    out = []
    for r in rows:
        c = dict(r)
        c["focus"] = json.loads(c["focus"]) if isinstance(c["focus"], str) else c["focus"]
        c["url"] = urls.get(c.pop("image_key"))
        out.append(c)
    return out


@router.get("/api/admin/marketing/captures")
async def list_captures(request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        rows = (await conn.execute(text(
            f"select {CAPTURE_FIELDS} from public.marketing_captures order by created_at"))).mappings().all()
    return {"captures": await _captures_out(request, rows)}


@router.post("/api/admin/marketing/captures/upload")
async def capture_upload(request: Request, user_id: UserId, ext: Literal["png", "jpg", "webp"] = "png"):
    """Where the browser puts a screenshot (straight to storage)."""
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
    key = f"captures/{uuid.uuid4().hex[:12]}.{ext}"
    return {"key": key, "upload_url": await request.app.state.storage.upload_url(key, bucket=BUCKET)}


@router.post("/api/admin/marketing/captures", status_code=201)
async def new_capture(body: NewCapture, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id)
        row = (await conn.execute(text(
            f"""insert into public.marketing_captures (name, image_key, width, height, created_by)
                values (:n, :k, :w, :h, :u) returning {CAPTURE_FIELDS}"""),
            {"n": body.name, "k": body.key, "w": body.width, "h": body.height, "u": user_id})).mappings().one()
    return {"capture": (await _captures_out(request, [row]))[0]}


@router.patch("/api/admin/marketing/captures/{capture_id}")
async def edit_capture(capture_id: uuid.UUID, body: CaptureEdit, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id)
        row = (await conn.execute(text(
            f"""update public.marketing_captures set name = coalesce(:n, name), description = coalesce(:d, description),
                       focus = coalesce(cast(:f as jsonb), focus)
                 where id = :id returning {CAPTURE_FIELDS}"""),
            {"id": capture_id, "n": body.name, "d": body.description,
             "f": None if body.focus is None else json.dumps([p.model_dump() for p in body.focus])})).mappings().first()
    if row is None:
        raise ApiError(404, "not_found", "Esa captura no existe.")
    return {"capture": (await _captures_out(request, [row]))[0]}


@router.delete("/api/admin/marketing/captures/{capture_id}", status_code=204)
async def delete_capture(capture_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id)
        key = (await conn.execute(text("delete from public.marketing_captures where id = :id returning image_key"),
                                  {"id": capture_id})).scalar()
    if key:
        try:
            await request.app.state.storage.delete(key, bucket=BUCKET)
        except Exception:  # the row is gone; a stray file in the bucket harms nothing
            log.warning("capture file %s not deleted", key)
