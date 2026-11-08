"""Promotional videos for /admin/marketing: DeepSeek writes the script of a template from a real tome; the video
itself is drawn and rendered in the admin's browser (frontend/src/video)."""

from typing import Annotated

from pydantic import BaseModel, Field

from app.agents import AgentResult, _json_call
from app.llm import LLM

Line = Annotated[str, Field(min_length=2, max_length=60)]


class VideoScript(BaseModel):
    """«De un tema a un libro en 30 s»: the words on screen, scene by scene."""

    hook: Line  # the first two seconds: stops the scroll
    request: Annotated[str, Field(min_length=10, max_length=140)]  # what the teacher types in the composer
    plan: Line  # caption while the outline appears
    cover: Line  # while the cover is painted
    pages: Line  # while the pages go by
    pdf: Line  # the finished PDF
    cta: Line  # the closing call to action
    post: Annotated[str, Field(max_length=700)] = ""  # the text to publish with it, hashtags included


SCRIPT_SYSTEM = """Eres guionista de videos cortos para redes (Reels, TikTok, Shorts) de una startup: Jelyx Docs, que
crea en minutos libros y cuadernillos educativos ilustrados en español sobre el tema que escribas (portada,
ilustraciones con los mismos personajes, actividades y solucionario, PDF listo para imprimir).

Escribes los textos en pantalla de un video de 30 segundos que muestra un libro real hecho con la app. El público son
docentes y madres y padres de habla hispana. Reglas:
- Español neutro, tuteo, frases cortas y concretas. Nada de «revolucionario», «increíble» ni «IA» en el gancho.
- hook: lo que siente el docente (un dolor o un deseo), máximo 45 caracteres; tiene que hacer parar el scroll.
- request: el pedido que la docente escribe, en primera persona y natural, sobre el tema del libro (máximo 120).
- plan, cover, pages, pdf: un subtítulo por escena, máximo 40 caracteres cada uno, que cuente lo que se ve.
- cta: máximo 40 caracteres, invita a probarlo gratis.
- post: el texto de la publicación (3 o 4 líneas y 4 a 6 hashtags en español).

Responde solo con json: {"hook", "request", "plan", "cover", "pages", "pdf", "cta", "post"}"""


async def video_script(llm: LLM, *, title: str, topic: str, kind: str, audience: str, sections: list[str],
                       angle: str | None = None) -> AgentResult[VideoScript]:
    tome = (f"Libro: {title}\nTipo: {kind}\nTema pedido: {topic}\nPara: {audience or 'sin indicar'}\n"
            f"Secciones: {'; '.join(sections[:8]) or 'sin secciones'}")
    if angle:
        tome += f"\nEnfoque que pide el equipo: {angle}"
    messages = [{"role": "system", "content": SCRIPT_SYSTEM}, {"role": "user", "content": tome}]
    return await _json_call(llm, messages, VideoScript, temperature=1.0, max_tokens=1200)
