"""Promotional videos for /admin/marketing: DeepSeek writes the script of a template from a real tome; the video
itself is drawn and rendered in the admin's browser (frontend/src/video)."""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field

from app.agents import AgentResult, _json_call
from app.llm import LLM



def _clip(limit: int):
    """A line a little too long is cut at its last whole word, never a reason to throw the whole script away."""
    def clip(v):
        if not isinstance(v, str):
            return v
        v = " ".join(v.split())
        return v if len(v) <= limit else v[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return BeforeValidator(clip)


Line = Annotated[str, _clip(60), Field(min_length=2, max_length=60)]


class VideoScript(BaseModel):
    """«De un tema a un libro en 30 s»: the words on screen, scene by scene."""

    hook: Line  # the first two seconds: stops the scroll
    request: Annotated[str, _clip(140), Field(min_length=10, max_length=140)]  # what the teacher types in the composer
    plan: Line  # caption while the outline appears
    cover: Line  # while the cover is painted
    pages: Line  # while the pages go by
    pdf: Line  # the finished PDF
    cta: Line  # the closing call to action
    post: Annotated[str, _clip(700), Field(max_length=700)] = ""  # the text to publish with it, hashtags included
    voiceover: Annotated[str, _clip(700), Field(max_length=700)] = ""  # what a voice app reads over the 30 seconds


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
- voiceover: la locución para leer con una app de voz sobre los 30 segundos: de 60 a 75 palabras, tono cercano y
  natural, en el orden de las escenas (gancho, pedido, plan, portada, páginas, PDF, cierre), sin repetir palabra por
  palabra los textos en pantalla. Escrita para el oído: sin emojis, hashtags ni símbolos; la dirección se dice
  «docs punto jelyx punto app».

Responde solo con json: {"hook", "request", "plan", "cover", "pages", "pdf", "cta", "post", "voiceover"}"""


async def video_script(llm: LLM, *, title: str, topic: str, kind: str, audience: str, sections: list[str],
                       angle: str | None = None) -> AgentResult[VideoScript]:
    tome = (f"Libro: {title}\nTipo: {kind}\nTema pedido: {topic}\nPara: {audience or 'sin indicar'}\n"
            f"Secciones: {'; '.join(sections[:8]) or 'sin secciones'}")
    if angle:
        tome += f"\nEnfoque que pide el equipo: {angle}"
    messages = [{"role": "system", "content": SCRIPT_SYSTEM}, {"role": "user", "content": tome}]
    return await _json_call(llm, messages, VideoScript, temperature=1.0, max_tokens=1200)


# The director: any video asked for in words, built from scenes that animate the real app (frontend/src/video).
SCENES = {
    "title": "texto grande animado a pantalla completa: el gancho, el título del tutorial o una idea clave",
    "compose": "la docente escribe su pedido en la app y pulsa «Crear mi libro» (text: el pedido, en primera persona)",
    "plan": "aparece el plan del libro con sus secciones reales",
    "cover": "la portada real del libro se pinta",
    "pages": "las páginas ilustradas del libro pasan como al hojearlo",
    "pdf": "el PDF terminado, con solucionario, nombre y logo, listo para imprimir",
    "editor_open": "se abre el Editor de páginas: la tira de miniaturas y el cursor elige una página",
    "editor_move": "en el editor, el cursor arrastra la pregunta a otro lugar de la lámina («Mover textos»)",
    "editor_facts": "en el editor, se quita un dato de la lámina con ✕ y se añade otro con «+ Añadir dato» "
                    "(text: el dato nuevo, máximo 60 caracteres)",
    "editor_repaint": "en el editor, se escribe qué cambiar y se pulsa «Repintar»: la ilustración se pinta de nuevo "
                      "(text: la instrucción, p. ej. «que Laura señale el cielo»)",
    "editor_cover": "en el editor, la portada: se quitan la línea «Nombre» y el sello de edad con un clic",
    "editor_save": "«Guardar cambios»: el próximo PDF ya sale con todo lo editado",
    "cta": "cierre con la marca, la llamada a la acción y la dirección de la app",
}
SceneType = Literal["title", "compose", "plan", "cover", "pages", "pdf", "editor_open", "editor_move", "editor_facts",
                    "editor_repaint", "editor_cover", "editor_save", "cta"]
TEXT_SCENES = {"compose", "editor_facts", "editor_repaint"}  # the scenes that type something on screen


class Scene(BaseModel):
    type: SceneType
    seconds: float = Field(default=4, ge=1, le=15)
    caption: Annotated[str, _clip(70), Field(max_length=70)] = ""  # the line on screen
    voice: Annotated[str, _clip(300), Field(max_length=300)] = ""  # what the voiceover says meanwhile
    text: Annotated[str, _clip(140), Field(max_length=140)] = ""  # what the scene types (TEXT_SCENES)


class Storyboard(BaseModel):
    kind: Literal["marketing", "explainer", "tutorial"] = "marketing"
    duration: Literal[15, 30, 45, 60] = 30
    title: Annotated[str, _clip(80), Field(min_length=2, max_length=80)]
    scenes: list[Scene] = Field(min_length=2, max_length=16)
    post: Annotated[str, _clip(700), Field(max_length=700)] = ""

    @property
    def voiceover(self) -> str:
        return " ".join(s.voice.strip() for s in self.scenes if s.voice.strip())


def tidy_storyboard(board: Storyboard) -> Storyboard:
    """What the code guarantees whatever the director wrote: it opens on a title, ends on the call to action, a
    typing scene has something to type, and the scenes fill exactly the length asked for."""
    scenes = [s for s in board.scenes if s.type != "cta" or s is board.scenes[-1]]
    if scenes[0].type != "title":
        scenes.insert(0, Scene(type="title", seconds=3, caption=board.title))
    if scenes[-1].type != "cta":
        scenes.append(Scene(type="cta", seconds=3, caption="Pruébalo gratis"))
    for s in scenes:
        if s.type in TEXT_SCENES and not s.text:
            s.text = {"compose": "Quiero un libro ilustrado para mi grupo",
                      "editor_facts": "Dato nuevo para la lámina",
                      "editor_repaint": "más luz de mañana"}[s.type]
    scale = board.duration / sum(s.seconds for s in scenes)
    for s in scenes:
        s.seconds = round(max(1.5, s.seconds * scale), 2)
    board.scenes = scenes[:16]
    return board


DIRECTOR_SYSTEM = """Eres director de videos cortos de producto de una startup, como los de las apps modernas en
redes: Jelyx Docs crea en minutos libros y cuadernillos educativos ilustrados en español (portada, ilustraciones con
los mismos personajes, actividades, solucionario, PDF para imprimir) y tiene un Editor de páginas para corregirlos.

Recibes el pedido del equipo, el tipo de video, la duración y un libro real hecho con la app. Armas el storyboard
solo con estas escenas, que ya existen animadas con la app real:
""" + "\n".join(f"- {k}: {v}" for k, v in SCENES.items()) + """

Tipos de video:
- marketing: para vender. Abre con un gancho (title) que nombra un dolor o un deseo del docente, ritmo rápido
  (2 a 4 s por escena), muestra el resultado y cierra con cta.
- explainer: explica cómo funciona la app de principio a fin, claro y sin frases de venta; cierra con cta.
- tutorial: enseña a hacer algo en la app. Abre con title («Cómo …»), luego un paso por escena, en el orden en que
  se hace de verdad y con calma (4 a 7 s por paso; el código los numera «Paso 1, 2…»), y cierra con cta.
  Elige solo las escenas que enseñan lo pedido.

Reglas: español neutro, tuteo, frases cortas. caption: máximo 50 caracteres, lo que se ve o lo que se aprende en esa
escena. voice: la locución de esa escena, natural, para una app de voz (unas 2,5 palabras por segundo de la escena;
sin emojis ni símbolos; la dirección se dice «docs punto jelyx punto app»). La suma de seconds es la duración pedida.
post: el texto para publicar (3 o 4 líneas y 4 a 6 hashtags).

Responde solo con json:
{"title": "…", "scenes": [{"type": "…", "seconds": 4, "caption": "…", "voice": "…", "text": "…"}], "post": "…"}"""


async def director(llm: LLM, *, ask: str, kind: str, duration: int, title: str, topic: str, book_kind: str,
                   audience: str, sections: list[str], sample: str | None) -> AgentResult[Storyboard]:
    facts = (f"Pedido del equipo: {ask}\nTipo de video: {kind}\nDuración: {duration} segundos\n\n"
             f"Libro que se muestra: {title}\nTipo: {book_kind}\nTema: {topic}\nPara: {audience or 'sin indicar'}\n"
             f"Secciones: {'; '.join(sections[:8]) or 'sin secciones'}")
    if sample:
        facts += f"\nUna de sus láminas: {sample}"
    messages = [{"role": "system", "content": DIRECTOR_SYSTEM}, {"role": "user", "content": facts}]
    result = await _json_call(llm, messages, Storyboard, temperature=0.9, max_tokens=3000)
    result.value.kind, result.value.duration = kind, duration  # what the team asked, not what the model echoed
    result.value = tidy_storyboard(result.value)
    return result
