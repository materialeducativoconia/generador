"""The order summary: before a tome exists (and before any credit is spent) the user reads what will be made, in plain
words, and confirms or goes back to adjust the request. DeepSeek writes it; it costs the user nothing."""

import logging
import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app import credits
from app.agents import AgentFailed, _json_call
from app.api.adopters import log_event, recent
from app.api.deps import current_user_id
from app.api.series import NewTome
from app.errors import ApiError
from app.llm import UpstreamAuthError, UpstreamError
from app.plans import PAID, tome_credits
from app.render import GENRE_LABEL

log = logging.getLogger("api")
router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
SUMMARIES_PER_DAY = 40  # one DeepSeek call each, on us

SUMMARY_SYSTEM = """Eres quien toma el pedido en Jelyx Docs, una app que crea libros y cuadernillos educativos
ilustrados en español (portada, páginas ilustradas, actividades, solucionario, PDF para imprimir). Antes de crear
nada, le muestras al docente un resumen de su pedido para que confirme o lo ajuste.

Lees el pedido y las opciones elegidas y escribes, sin inventar lo que no se pidió:
- title: un título tentativo para el libro.
- kind: qué tipo de material será (libro ilustrado, cuento, libro para colorear, cuadernillo de fichas, método paso a
  paso o secuencia didáctica). Si el formato ya está elegido, ese.
- audience: para quién (edad o grado), tal como lo dice el pedido o la opción elegida.
- sections: cómo se repartirían las páginas: de 1 a 6 secciones con un título breve y sus páginas; la suma de pages
  es exactamente el total de páginas elegido.
- includes: 3 a 5 cosas concretas que tendrá (p. ej. «Ilustraciones en cada página», «Preguntas de comprensión»,
  «Solucionario al final»).
- notes: 0 a 3 avisos útiles para ajustar antes de confirmar: algo ambiguo, algo que no cabe en esas páginas, o una
  sugerencia corta. Vacío si el pedido está claro.

Español neutro, tuteo, frases cortas. Responde solo con json:
{"title": "…", "kind": "…", "audience": "…", "sections": [{"title": "…", "pages": 2}], "includes": ["…"],
 "notes": ["…"]}"""


class Part(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    pages: int = Field(ge=1, le=200)


class Summary(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=80)
    audience: str = Field(default="", max_length=120)
    sections: list[Part] = Field(min_length=1, max_length=20)
    includes: list[str] = Field(default=[], max_length=6)
    notes: list[str] = Field(default=[], max_length=4)


@router.post("/api/series/summary")
async def order_summary(body: NewTome, request: Request, user_id: UserId):
    """What the tome will be and what it will cost, for the user to confirm; nothing is created or charged."""
    async with request.app.state.engine.connect() as conn:
        if await recent(conn, user_id, "tome_summary", timedelta(days=1)) >= SUMMARIES_PER_DAY:
            raise ApiError(429, "rate_limited", "Llegaste al máximo de resúmenes por hoy; crea el tomo o vuelve mañana.")
        acc = await credits.account(conn, user_id)
        wallet = await credits.balance(conn, acc.org_id)
    summary, ai = None, False
    if request.app.state.llm is not None:
        options = (f"Pedido: {body.request}\nPúblico elegido: {body.audience or 'el que diga el pedido'}\n"
                   f"Formato: {GENRE_LABEL.get(body.format, 'automático (lo decide la app)')}\n"
                   f"Páginas de contenido: {body.page_count}\n"
                   f"Secciones: {body.section_count or 'las que convengan'}\n"
                   f"Instrucciones extra: {body.extra_instructions or 'ninguna'}")
        try:
            summary = (await _json_call(request.app.state.llm, [{"role": "system", "content": SUMMARY_SYSTEM},
                                                                 {"role": "user", "content": options}],
                                        Summary, temperature=0.3, max_tokens=1200)).value
            ai = True
        except (AgentFailed, UpstreamError, UpstreamAuthError) as exc:
            log.warning("order summary failed: %s", exc)
    summary = fit(summary or plain(body), body)
    free = acc.plan_key not in PAID and wallet["total"] == 0
    cost = tome_credits(body.page_count)
    async with request.app.state.engine.begin() as conn:
        await log_event(conn, user_id, "tome_summary", {"request": body.request[:300], "pages": body.page_count,
                                                        "format": body.format, "ai": ai})
    return {"summary": summary.model_dump(), "ai": ai, "credits": cost, "now": 5, "balance": wallet["total"],
            "free_preview": free}


def fit(summary: Summary, body: NewTome) -> Summary:
    """The page split adds up to the pages chosen (and keeps the sections asked for), whatever the model wrote."""
    parts = summary.sections[: body.section_count or 20][: body.page_count]
    total = body.page_count
    if body.section_count and len(parts) < body.section_count:
        parts += [Part(title=f"Sección {i + 1}", pages=1) for i in range(len(parts), min(body.section_count, total))]
    pages = [max(1, p.pages) for p in parts]
    while sum(pages) > total:
        pages[pages.index(max(pages))] -= 1
    i = 0
    while sum(pages) < total:
        pages[i % len(pages)] += 1
        i += 1
    summary.sections = [Part(title=p.title, pages=n) for p, n in zip(parts, pages, strict=True)]
    return summary


def plain(body: NewTome) -> Summary:
    """Without DeepSeek: the request said back as it was asked."""
    return Summary(title=body.request[:120], kind=GENRE_LABEL.get(body.format, "Material educativo"),
                   audience=body.audience, sections=[Part(title="Contenido", pages=body.page_count)],
                   includes=["Portada ilustrada", "Páginas con ilustraciones y actividades", "Solucionario"])
