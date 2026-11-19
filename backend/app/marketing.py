"""Promotional videos for /admin/marketing: DeepSeek writes the script of a template from a real tome; the video
itself is drawn and rendered in the admin's browser (frontend/src/video)."""

import math
import random
import re
from typing import Annotated, Literal

from dataclasses import dataclass

from pydantic import BaseModel, BeforeValidator, Field

from app.agents import AgentFailed, AgentResult, _json_call
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
    "list": "una lista grande de 2 a 4 puntos que entran uno a uno (text: los puntos separados por « | », "
            "cada uno de máximo 30 caracteres)",
    "versus": "pantalla partida, antes y después (text: «lo de antes | lo de ahora», p. ej. "
              "«3 horas en Word | 5 minutos con Jelyx»)",
    "number": "un número enorme que cuenta hasta su valor (text: el número con su unidad, p. ej. «5 min» o «24 "
              "páginas»; caption: lo que significa)",
    "formats": "los tipos de libro que hace la app (libro ilustrado, cuento, para colorear, cuadernillo de fichas, "
               "método paso a paso, secuencia didáctica), cada uno con la portada real de un libro hecho con la app",
    "characters": "los personajes del libro: sus hojas de modelo aparecen con su nombre y luego salen iguales en "
                  "varias páginas (los mismos personajes en todo el libro)",
    "screen": "una captura REAL de la app en un teléfono o una laptop: la cámara se acerca al punto marcado y el "
              "cursor hace clic (capture: el id de la captura; focus: el número del punto, desde 0). Solo con las "
              "capturas de la lista; es lo más creíble para tutoriales y explicativos",
    "phone": "la app en un iPhone que flota: se escribe el pedido, se pinta la portada y pasan las páginas, con "
             "insignias «Portada», «N páginas», «PDF listo» (text: el pedido que se escribe, máximo 70 caracteres)",
    "devices": "el libro abierto a la vez en una laptop y en un iPhone: se usa en cualquier dispositivo",
    "zoom": "una página real y una lupa que la recorre; luego la cámara se acerca al detalle y una etiqueta lo nombra "
            "(text: la etiqueta, máximo 30 caracteres, p. ej. «Mismos personajes»)",
    "kinetic": "tipografía cinética de lanzamiento: frases cortas a pantalla completa, una tras otra, que golpean con "
               "colores alternos (text: 2 a 4 frases de 1 a 3 palabras separadas por « | »; el caption no se muestra)",
    "bento": "cuadrícula bento de funciones como en las webs de startups: la portada en la celda grande y hasta 4 "
             "funciones con icono (text: las funciones separadas por « | », cada una de máximo 26 caracteres)",
    "chat": "el chat con la IA, como en las apps que crean con un prompt: se escribe el pedido y se envía, la IA "
            "marca sus pasos (plan, portada, ilustraciones) y responde con el libro terminado (text: el pedido)",
    "logo": "revelado del logo de Jelyx Docs con un anillo de luz y el caption como lema: una apertura de marca",
    "motion": "motion graphic: formas, iconos y líneas animadas que explican una idea sin mostrar la app. Lo describes "
              "tú en el campo motion (estilo, elementos y colores) a partir del pedido; text: la frase central, "
              "máximo 40 caracteres",
    "cta": "cierre con la marca, la llamada a la acción y la dirección de la app",
}
SceneType = Literal["title", "compose", "plan", "cover", "pages", "pdf", "editor_open", "editor_move", "editor_facts",
                    "editor_repaint", "editor_cover", "editor_save", "list", "versus", "number", "formats", "characters", "screen",
                    "phone", "devices", "zoom", "kinetic", "bento", "chat", "logo", "motion", "cta"]
# The scenes that show a text of their own, and what they show when the director left it empty.
TEXT_SCENES = {"compose": "Quiero un libro ilustrado para mi grupo", "editor_facts": "Dato nuevo para la lámina",
               "editor_repaint": "más luz de mañana", "list": "Portada | Ilustraciones | Actividades | Solucionario",
               "versus": "Horas armando material | Minutos con Jelyx", "number": "5 min",
               "phone": "Cuento del ciclo del agua para 2.º grado", "chat": "Un libro ilustrado de los planetas para 3.º",
               "zoom": "Cada detalle, ilustrado", "kinetic": "Tu tema | Tu grupo | Tu libro",
               "bento": "Ilustraciones únicas | Mismos personajes | Solucionario | PDF y Word",
               "motion": "Tu tema, tu libro"}
BOOK_SCENES = {"cover", "pages", "pdf"}  # a video may open on the finished book instead of a title
OPENERS = {"title", "logo", "kinetic", "chat", "phone", "motion"}  # scenes that open a video by themselves

# How the story is told: without one the director falls back on the app's flow every time, and every video looks alike.
Kind = Literal["marketing", "explainer", "tutorial", "motion"]
STRUCTURES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "problema": ("Problema y solución", ("marketing", "explainer"),
                 "abre nombrando un dolor concreto del docente (title o number), lo agrava en una escena (versus o "
                 "title) y luego la app lo resuelve con dos o tres escenas del libro; cierra con cta."),
    "antes_despues": ("Antes y después", ("marketing",),
                      "la segunda escena es un versus (antes | con Jelyx); luego el «después» se muestra con escenas de "
                      "la app y un number con el tiempo ahorrado; cierra con cta."),
    "razones": ("3 razones", ("marketing", "explainer"),
                "title «3 razones para …»; luego una escena de la app por razón, con caption que empieza «1.», «2.», "
                "«3.»; antes del cta, un list que las resume."),
    "resultado": ("Resultado primero", ("marketing",),
                  "abre con el libro terminado (pages o pdf, sin title al inicio) y un caption que sorprende; luego "
                  "cuenta en pocas escenas cómo se hizo (compose, plan, cover) y cierra con cta."),
    "historia": ("Un día de la docente", ("marketing", "explainer"),
                 "una pequeña historia con hora: title «Domingo, 9 de la noche…», compose, cover, pages, otro title "
                 "«Lunes: la clase está lista» y cta. Voz en primera persona de la docente."),
    "pregunta": ("Pregunta y respuesta", ("marketing", "explainer"),
                 "title con una pregunta que se hace el docente; cada escena siguiente la responde con algo que se ve "
                 "en la app; cierra con cta."),
    "demo": ("De principio a fin", ("explainer",),
             "el recorrido completo: compose, plan, cover, pages, pdf y una o dos escenas del editor; un number al "
             "final con el tiempo total."),
    "pasos": ("Paso a paso", ("tutorial",),
              "title «Cómo …», un paso por escena en el orden real, y cta."),
    "truco": ("Truco rápido", ("tutorial",),
              "title «Truco: …», solo dos o tres escenas con lo pedido, bien explicadas, y cta."),
    "lanzamiento": ("Lanzamiento de startup", ("marketing",),
                    "como el video de lanzamiento de una app de IA: logo o kinetic de apertura, phone con el pedido, "
                    "zoom a un detalle, bento con las funciones, devices y cta. Ritmo rápido, frases de impacto."),
    "prompt": ("Del prompt al libro", ("marketing", "explainer"),
               "abre con chat (el pedido escrito a la IA), sigue con phone o cover y pages mostrando el resultado, un "
               "number con el tiempo y cta. La idea: escribes una frase y obtienes un libro."),
    "funciones": ("Recorrido de funciones", ("explainer", "marketing"),
                  "title con la promesa, bento con 4 funciones, luego una escena de la app por función (zoom, "
                  "characters, pdf o editor) y devices antes del cta."),
    "lista": ("3 cosas que no sabías", ("tutorial", "explainer"),
              "title «3 cosas que puedes hacer en …», un list con las tres, luego una escena de la app por cada una "
              "con caption que empieza «1.», «2.», «3.», y cta."),
    "motion_explica": ("Explicación animada", ("motion",),
                       "abre con kinetic o un motion burst, explica la idea en 3 o 4 escenas motion de estilos distintos "
                       "(flow para el proceso, orbit para lo que reúne, stats para los números), una sola escena del "
                       "libro (cover o pages) como prueba y cta."),
    "motion_datos": ("Infografía animada", ("motion",),
                     "title con la pregunta o el dato que sorprende, motion stats con los números del pedido, un "
                     "number, motion flow con el cómo, pages y cta."),
    "motion_marca": ("Manifiesto de marca", ("motion", "marketing"),
                     "logo de apertura, tres escenas motion con una idea cada una (burst, orbit, grid), un kinetic con "
                     "el lema y cta. Ritmo rápido, sin escenas del editor."),
}
LOOKS = ("claro", "oscuro", "color", "noche")


def pick_structure(kind: str, last: str | None = None) -> str:
    """Automatic: one of the kind's structures, never the one its last video used."""
    fits = [k for k, (_, kinds, _) in STRUCTURES.items() if kind in kinds]
    return random.choice([k for k in fits if k != last] or fits)


# Motion graphics: the director describes each one (its "prompt") and the browser draws it (frontend/src/video/motion.tsx).
MOTION_STYLES = {
    "flow": "los elementos en fila unidos por una línea que se dibuja, uno tras otro: un proceso o pasos",
    "orbit": "la frase en el centro y los elementos en burbujas que giran alrededor: lo que algo reúne",
    "burst": "formas de colores que estallan desde el centro y se ordenan alrededor de la frase: un impacto, una idea",
    "stats": "barras que crecen con su valor (value: el número, p. ej. «85%» o «3 h») y su etiqueta: datos",
    "grid": "los elementos en tarjetas que entran en ola, con formas que giran detrás: una lista de beneficios",
}
MotionStyle = Literal["flow", "orbit", "burst", "stats", "grid"]
ICONS = ("sparkle", "book", "pencil", "clock", "star", "heart", "check", "palette", "download", "people", "idea",
         "rocket", "puzzle", "globe", "apple", "music", "leaf", "calculator", "school", "printer")
Icon = Annotated[Literal[ICONS], BeforeValidator(lambda v: v if v in ICONS else "sparkle")]


class MotionItem(BaseModel):
    icon: Icon = "sparkle"
    label: Annotated[str, _clip(28), Field(max_length=28)] = ""
    value: Annotated[str, _clip(12), Field(max_length=12)] = ""  # stats: the number the bar shows


def _hexes(v):
    """Up to three colours; anything that is not a #rrggbb is dropped, never a reason to throw the storyboard away."""
    ok = lambda c: isinstance(c, str) and len(c) == 7 and c[0] == "#" and all(x in "0123456789abcdefABCDEF" for x in c[1:])
    return [c for c in v if ok(c)][:3] if isinstance(v, list) else []


class Motion(BaseModel):
    style: Annotated[MotionStyle, BeforeValidator(lambda v: v if v in MOTION_STYLES else "burst")] = "burst"
    items: Annotated[list[MotionItem], BeforeValidator(lambda v: v[:6] if isinstance(v, list) else [])] = Field(default_factory=list)
    colors: Annotated[list[str], BeforeValidator(_hexes)] = Field(default_factory=list)  # empty: the look's


class Scene(BaseModel):
    type: SceneType
    seconds: float = Field(default=4, ge=1, le=15)
    caption: Annotated[str, _clip(70), Field(max_length=70)] = ""  # the line on screen
    voice: Annotated[str, _clip(300), Field(max_length=300)] = ""  # what the voiceover says meanwhile
    text: Annotated[str, _clip(140), Field(max_length=140)] = ""  # what the scene types (TEXT_SCENES)
    capture: str = ""  # a screen scene's capture (marketing_captures id)
    focus: int = Field(default=0, ge=0, le=20)  # and which of its marked points the camera goes to
    motion: Motion | None = None  # a motion scene's graphic, as the director described it
    code: str = Field(default="", max_length=24000)  # «a medida»: the scene as Claude programmed it (drawn over its type)


# Free music (Kevin MacLeod, incompetech.com, CC BY 4.0: free to use crediting him), cut to 100 s in
# frontend/public/video-audio/<key>.mp3, with its tempo and its first beat so the cuts land on the beat.
MUSIC = {
    "wallpaper": ("Wallpaper", "Moderno, de startup", 124.0, 0.020),
    "inspired": ("Inspired", "Inspirador", 120.0, 0.021),
    "carefree": ("Carefree", "Alegre y ligero", 96.0, 0.026),
    "forecast": ("Local Forecast - Elevator", "Tranquilo", 123.0, 0.325),
}
KIND_MUSIC = {"marketing": "wallpaper", "explainer": "carefree", "tutorial": "forecast", "motion": "inspired"}


def music_credit(key: str) -> str:
    return f"Música: «{MUSIC[key][0]}», Kevin MacLeod (incompetech.com), CC BY 4.0"


def pick_music(asked: str, kind: str) -> str | None:
    """«auto»: the kind's track; «none»: silence; else the track asked for."""
    return None if asked == "none" else KIND_MUSIC.get(kind) if asked == "auto" else asked if asked in MUSIC else None


class Storyboard(BaseModel):
    kind: Kind = "marketing"
    duration: int = Field(default=30, ge=5, le=180)
    source: Literal["ask", "script"] = "ask"  # directed from a request, or from the team's own script (its words are the voice)
    music: Annotated[str | None, BeforeValidator(lambda v: v if v in MUSIC else None)] = None
    sfx: bool = True  # a whoosh on each cut, a hit on the close
    structure: str = ""  # a key of STRUCTURES
    look: Literal["claro", "oscuro", "color", "noche"] = "claro"  # the colours of the text scenes
    transition: Literal["mixta", "deslizar", "zoom", "barrido", "corte"] = "mixta"  # how one scene gives way to the next
    title: Annotated[str, _clip(80), Field(min_length=2, max_length=80)]
    scenes: list[Scene] = Field(min_length=1, max_length=24)
    post: Annotated[str, _clip(700), Field(max_length=700)] = ""

    @property
    def voiceover(self) -> str:
        return " ".join(s.voice.strip() for s in self.scenes if s.voice.strip())


def tidy_storyboard(board: Storyboard) -> Storyboard:
    """What the code guarantees whatever the director wrote: it opens on a title (or on the finished book), ends on
    the call to action, a scene with a text of its own has one, and the scenes fill exactly the length asked for.
    A video from the team's script keeps its scenes as written and lasts what its voice takes. With music, every
    cut lands on a beat."""
    scenes = list(board.scenes)
    if board.source == "ask":
        scenes = [s for s in scenes if s.type != "cta" or s is board.scenes[-1]]
        if scenes[0].type not in OPENERS and not (scenes[0].type in BOOK_SCENES and scenes[0].caption):
            scenes.insert(0, Scene(type="title", seconds=3, caption=board.title))
        if scenes[-1].type != "cta":
            scenes.append(Scene(type="cta", seconds=3, caption="Pruébalo gratis"))
    for s in scenes:
        if s.type in TEXT_SCENES and not s.text:
            s.text = TEXT_SCENES[s.type]
        if s.type != "motion":
            s.motion = None
        elif not (s.motion and s.motion.items):  # never an empty graphic: the caption's words, each with an icon
            words = [w.strip(".,;:¡!¿?") for w in (s.caption or board.title).split() if len(w) > 3][:4] or ["Jelyx"]
            s.motion = Motion(style=s.motion.style if s.motion else "burst", colors=s.motion.colors if s.motion else [],
                              items=[MotionItem(icon=ICONS[i], label=w) for i, w in enumerate(words)])
    if board.source == "ask":
        scale = board.duration / sum(s.seconds for s in scenes)
        for s in scenes:
            s.seconds = round(max(1.5, s.seconds * scale), 2)
    board.scenes = scenes[:24]
    if board.music:
        on_the_beat(board)
        credit = music_credit(board.music)
        if credit not in board.post:
            board.post = (board.post.rstrip() + "\n\n" + credit).strip()[-700:]
    if board.source == "script":
        board.duration = max(5, min(180, round(sum(s.seconds for s in board.scenes))))
    return board


def on_the_beat(board: Storyboard) -> None:
    """Each cut moved to a beat of the music: the nearest one for a directed video (its length stays), the next one for
    a script's (a scene never ends before its voice does)."""
    _, _, bpm, first = MUSIC[board.music]
    beat = 60 / bpm
    planned = cut = 0.0
    for s in board.scenes:
        planned += s.seconds
        want = cut + s.seconds if board.source == "script" else planned
        n = (want - first) / beat
        at = first + (math.ceil(n - 0.02) if board.source == "script" else round(n)) * beat  # 0.02: a saved cut stays put
        while at - cut < 1.5 - 1e-6:  # never a scene shorter than a second and a half
            at += beat
        s.seconds = round(min(15.0, at - cut), 3)
        cut += s.seconds


SCENE_LIST = "\n".join(f"- {k}: {v}" for k, v in SCENES.items())
MOTION_RULES = """La escena motion es un motion graphic que diseñas tú: lo describes en su campo motion,
{"style", "items": [{"icon", "label", "value"}], "colors"}:
- style, uno de: """ + "; ".join(f"{k}: {v}" for k, v in MOTION_STYLES.items()) + """.
- items: de 3 a 5 elementos, cada uno con icon (solo uno de: """ + ", ".join(ICONS) + """) y label de máximo 24
  caracteres que diga algo concreto (nunca «Función 1»); value solo en stats.
- colors: de 1 a 3 colores hex que vayan con el tema (p. ej. verdes y ocres para la selva), o vacío.
Varía el style entre escenas motion."""

DIRECTOR_SYSTEM = """Eres director de videos cortos de producto de una startup, como los de las apps modernas en
redes: Jelyx Docs crea en minutos libros y cuadernillos educativos ilustrados en español (portada, ilustraciones con
los mismos personajes, actividades, solucionario, PDF para imprimir) y tiene un Editor de páginas para corregirlos.

Recibes el pedido del equipo, el tipo de video, la duración y un libro real hecho con la app. Armas el storyboard
solo con estas escenas, que ya existen animadas con la app real:
""" + SCENE_LIST + """

""" + MOTION_RULES + """ Diséñalo a partir del pedido.

Las escenas list, versus, number y kinetic son texto animado: úsalas para variar el ritmo entre escenas de la app.
phone, devices, zoom, bento, chat y logo dan el acabado de los videos de lanzamiento de las startups de IA: úsalas
en marketing y explainer.

Acabado profesional, como un anuncio de producto hecho por un estudio:
- El gancho se entiende en los primeros 2 segundos: title de máximo 6 palabras o kinetic de 2 a 3 frases cortas.
- Nunca dos escenas de texto animado (title, list, versus, number, kinetic) seguidas: alterna texto y app.
- Una idea por escena; captions de máximo 7 palabras, sin repetir lo que la escena ya muestra escrito.
- Varía la duración: escenas de texto cortas (1,5 a 3 s), escenas de la app más largas (3 a 5 s en marketing).
- La última palabra del title es la que importa (sale resaltada): ponla al final («Tu clase lista en minutos»).
- Termina en alto: la escena anterior al cta muestra el resultado (pages, pdf, devices o number), no texto suelto.

Tipos de video:
- marketing: para vender. Abre con un gancho (title) que nombra un dolor o un deseo del docente, ritmo rápido
  (2 a 4 s por escena), muestra el resultado y cierra con cta.
- explainer: explica cómo funciona la app de principio a fin, claro y sin frases de venta; cierra con cta.
- motion: un video de motion graphics, como los de las marcas: la mayoría de las escenas son motion (y title,
  kinetic o number), con una o dos escenas del libro real como prueba; 2 a 4 s por escena; cierra con cta.
- tutorial: enseña a hacer algo en la app. Abre con title («Cómo …»), luego un paso por escena, en el orden en que
  se hace de verdad y con calma (4 a 7 s por paso; el código los numera «Paso 1, 2…»), y cierra con cta.
  Elige solo las escenas que enseñan lo pedido.

Reglas: español neutro, tuteo, frases cortas. caption: máximo 50 caracteres, lo que se ve o lo que se aprende en esa
escena. voice: la locución de esa escena, natural, para una app de voz: como máximo 2,5 palabras por segundo de la
escena (una escena de 2 s lleva 5 palabras; una de 4 s, 10), y una escena corta puede ir sin voz. Sin emojis ni
símbolos; la dirección se dice «docs punto jelyx punto app». La suma de seconds es la duración pedida.
post: el texto para publicar (3 o 4 líneas y 4 a 6 hashtags).

Responde solo con json:
{"title": "…", "scenes": [{"type": "…", "seconds": 4, "caption": "…", "voice": "…", "text": "…", "capture": "…",
"focus": 0, "motion": {"style": "…", "items": [{"icon": "…", "label": "…", "value": ""}], "colors": ["#…"]}}],
"post": "…"} (capture y focus solo en screen; motion solo en motion)"""


async def director(llm: LLM, *, ask: str, kind: str, duration: int, title: str, topic: str, book_kind: str,
                   audience: str, sections: list[str], sample: str | None, structure: str, cast: str | None = None,
                   recent: list[dict] = (), captures: list[dict] = ()) -> AgentResult[Storyboard]:
    """`recent`: the last storyboards ({title, scenes: [types]}), so this one is told another way. `captures`: the
    real screenshots of the app ({id, name, description, focus: [labels]}) its screen scenes may show."""
    name, _, how = STRUCTURES[structure]
    facts = (f"Pedido del equipo: {ask}\nTipo de video: {kind}\nDuración: {duration} segundos\n"
             f"Estructura: {name}: {how}\n\n"
             f"Libro que se muestra: {title}\nTipo: {book_kind}\nTema: {topic}\nPara: {audience or 'sin indicar'}\n"
             f"Secciones: {'; '.join(sections[:8]) or 'sin secciones'}")
    if sample:
        facts += f"\nUna de sus láminas: {sample}"
    facts += (f"\nPersonajes: {cast}" if cast else "\nEste libro no tiene personajes fijos: no uses la escena characters.")
    if recent:
        facts += ("\n\nVideos ya hechos: no repitas su secuencia de escenas, su gancho ni sus frases.\n"
                  + "\n".join(f"- «{r['title']}»: {' → '.join(r['scenes'])}" for r in recent))
    if captures:
        facts += ("\n\nCapturas reales de la app para las escenas screen (id: qué muestra; sus puntos, desde 0):\n"
                  + "\n".join(f"- {c['id']}: {c['name']}{' — ' + c['description'] if c['description'] else ''}"
                               f" | puntos: {'; '.join(f'{i} {p}' for i, p in enumerate(c['focus'])) or '0 centro'}"
                               for c in captures))
    else:
        facts += "\n\nNo hay capturas reales: no uses escenas screen."
    messages = [{"role": "system", "content": DIRECTOR_SYSTEM}, {"role": "user", "content": facts}]
    result = await _json_call(llm, messages, Storyboard, temperature=1.0, max_tokens=3000)
    known = {c["id"]: len(c["focus"]) for c in captures}
    result.value.scenes = [s for s in result.value.scenes if s.type != "screen" or s.capture in known] or result.value.scenes
    for s in result.value.scenes:
        if s.type == "screen":
            s.focus = min(s.focus, max(0, known[s.capture] - 1))
    result.value.kind, result.value.duration = kind, duration  # what the team asked, not what the model echoed
    result.value.structure, result.value.look = structure, random.choice(LOOKS)
    result.value = tidy_storyboard(result.value)
    long = overlong(result.value)
    if long:  # a voice longer than its scene is cut by the next one: the director shortens it, once
        messages += [{"role": "assistant", "content": result.value.model_dump_json(include={"scenes"})},
                     {"role": "user", "content": "La locución no cabe: " + "; ".join(long) + ". Reescribe solo esas "
                      "voces, más cortas y completas, sin cambiar las escenas. Responde solo con json: "
                      '{"voices": ["la voz de cada escena, en orden"]}'}]
        try:
            again = await _json_call(llm, messages, Voices, temperature=0.7, max_tokens=1500)
            if len(again.value.voices) == len(result.value.scenes):
                for scene, voice in zip(result.value.scenes, again.value.voices):
                    scene.voice = voice
        except AgentFailed:
            pass  # the first voices stay: the video plays them one after another
    return result


WORDS_PER_SECOND = 2.8  # what Gemini TTS reads at its natural pace


# «Desde mi guion»: the team writes the words; the voice reads them as they are and the director only decides how
# each one is shown.
MARKS = {"titulo": "title", "título": "title", "portada": "cover", "paginas": "pages", "páginas": "pages", "pdf": "pdf",
         "plan": "plan", "pedido": "compose", "escribir": "compose", "numero": "number", "número": "number",
         "lista": "list", "versus": "versus", "antes y despues": "versus", "antes y después": "versus",
         "frases": "kinetic", "cinetica": "kinetic", "cinética": "kinetic", "funciones": "bento", "chat": "chat",
         "telefono": "phone", "teléfono": "phone", "iphone": "phone", "dispositivos": "devices", "lupa": "zoom",
         "zoom": "zoom", "personajes": "characters", "formatos": "formats", "logo": "logo", "cierre": "cta",
         "editor": "editor_open", "captura": "screen", "pantalla": "screen", "motion": "motion"}
MARK_STYLES = {"proceso": "flow", "orbita": "orbit", "órbita": "orbit", "estallido": "burst", "datos": "stats",
               "tarjetas": "grid", **{k: k for k in MOTION_STYLES}}
SCRIPT_LIMIT = 24
_MARK = re.compile(r"^\s*\[([^\]]{1,40})\]\s*")
_LABEL = re.compile(r"^\s*(gancho|hook|cierre|escena\s*\d+)\s*[:.\-–]\s*", re.I)


@dataclass
class Beat:
    words: str
    type: str | None = None  # the scene the team fixed with a [mark]
    style: str | None = None  # and, for [motion …], its style

    @property
    def seconds(self) -> float:
        n = len(self.words.split())
        return round(min(14.0, max(2.0, n / WORDS_PER_SECOND + 0.6)), 2) if n else 2.5


def script_beats(script: str) -> list[Beat]:
    """The script cut into scenes: its paragraphs (or its lines, when it has no blank lines), a long one cut at its
    sentences. A line may start with a [mark] that fixes its scene: [portada], [motion órbita], [número]…"""
    text = script.replace("\r", "").strip()
    chunks = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text)] if re.search(r"\n\s*\n", text) \
        else [" ".join(line.split()) for line in text.split("\n")]
    beats: list[Beat] = []
    for chunk in filter(None, chunks):
        kind = style = None
        if m := _MARK.match(chunk):
            words = m.group(1).lower().split()
            for size in (3, 2, 1):  # «antes y después» is one mark
                key = " ".join(words[:size])
                if key in MARKS:
                    kind, rest = MARKS[key], words[size:]
                    style = next((MARK_STYLES[w] for w in rest if w in MARK_STYLES), None)
                    break
            chunk = chunk[m.end():]
        chunk = _LABEL.sub("", chunk).strip()
        parts, current = [], ""
        for sentence in re.split(r"(?<=[.!?¿¡…])\s+", chunk) if len(chunk.split()) > 32 else [chunk]:
            if current and len((current + " " + sentence).split()) > 32:
                parts.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        parts.append(current)
        beats += [Beat(p, kind if i == 0 else None, style if i == 0 else None) for i, p in enumerate(parts)]
    return [b for b in beats if b.words or b.type]


class ScriptScene(BaseModel):
    type: Annotated[SceneType, BeforeValidator(lambda v: v if v in SCENES else "motion")] = "motion"
    caption: Annotated[str, _clip(70), Field(max_length=70)] = ""
    text: Annotated[str, _clip(140), Field(max_length=140)] = ""
    capture: str = ""
    focus: int = Field(default=0, ge=0, le=20)
    motion: Motion | None = None


class ScriptBoard(BaseModel):
    title: Annotated[str, _clip(80), Field(min_length=2, max_length=80)]
    scenes: list[ScriptScene] = Field(default_factory=list)
    post: Annotated[str, _clip(700), Field(max_length=700)] = ""


SCRIPT_DIRECTOR_SYSTEM = """Eres director de arte de videos cortos de producto de una startup: Jelyx Docs crea en minutos
libros y cuadernillos educativos ilustrados en español (portada, ilustraciones con los mismos personajes, actividades,
solucionario, PDF para imprimir).

El equipo ya escribió el guion, dividido en escenas numeradas; la voz en off lee cada escena tal cual y tú NO la
cambias. Tu trabajo es decidir cómo se ve cada escena, solo con estas, que ya existen animadas con la app real:
""" + SCENE_LIST + """

""" + MOTION_RULES + """ Diséñalo a partir de lo que dice esa escena del guion.

Reglas:
- Exactamente una escena tuya por escena del guion, en el mismo orden.
- Si una escena trae «tipo fijado», usa ese type (y ese style si lo trae).
- Elige lo que muestra lo que dice la voz: si habla del libro, sus páginas o el PDF, usa cover, pages o pdf; si habla
  de escribir el tema o pedirlo, compose, chat o phone; tiempo, beneficios, pasos o ideas abstractas, motion; cifras,
  number o motion stats; la primera escena, un gancho (title, kinetic o motion); la última, si invita a probar, cta.
- Alterna: nunca el mismo type dos veces seguidas, salvo motion con estilos distintos.
- caption: el texto corto en pantalla, máximo 7 palabras, que resume la idea sin copiar la voz palabra por palabra. En
  title es el texto grande (máximo 6 palabras, la palabra clave al final); en cta, la llamada a la acción.
- text: solo en las escenas que lo piden (ver la lista).
title: el título del video. post: el texto para publicar (3 o 4 líneas y 4 a 6 hashtags).

Responde solo con json:
{"title": "…", "scenes": [{"type": "…", "caption": "…", "text": "…", "capture": "…", "focus": 0,
"motion": {"style": "…", "items": [{"icon": "…", "label": "…", "value": ""}], "colors": ["#…"]}}], "post": "…"}"""


async def script_director(llm: LLM, *, script: str, kind: str, title: str, topic: str, book_kind: str, audience: str,
                          sections: list[str], cast: str | None = None, captures: list[dict] = (),
                          music: str | None = None) -> AgentResult[Storyboard]:
    """The team's script as a storyboard: its words are the voice, scene by scene; DeepSeek picks and designs what
    each one shows, and each lasts what its voice takes. ValueError: an empty script, or one too long."""
    beats = script_beats(script)
    if not beats:
        raise ValueError("Escribe el guion: una línea o un párrafo por escena.")
    if len(beats) > SCRIPT_LIMIT:
        raise ValueError(f"El guion tiene {len(beats)} escenas; el máximo es {SCRIPT_LIMIT}. Junta algunas líneas.")
    if sum(b.seconds for b in beats) > 175:
        raise ValueError("El guion dura más de 3 minutos leído en voz alta; acórtalo.")
    lines = [f"{i + 1}. «{b.words}»" + (f" (tipo fijado: {b.type}{' ' + b.style if b.style else ''})" if b.type else "")
             for i, b in enumerate(beats)]
    facts = (f"Tipo de video: {kind}\nLibro que se muestra: {title}\nTipo: {book_kind}\nTema: {topic}\n"
             f"Para: {audience or 'sin indicar'}\nSecciones: {'; '.join(sections[:8]) or 'sin secciones'}\n"
             + (f"Personajes: {cast}\n" if cast else "Este libro no tiene personajes fijos: no uses characters.\n"))
    if captures:
        facts += ("Capturas reales para screen (id: qué muestra; sus puntos, desde 0):\n"
                  + "\n".join(f"- {c['id']}: {c['name']} | puntos: "
                               f"{'; '.join(f'{i} {p}' for i, p in enumerate(c['focus'])) or '0 centro'}" for c in captures) + "\n")
    else:
        facts += "No hay capturas reales: no uses screen.\n"
    facts += f"\nGuion ({len(beats)} escenas):\n" + "\n".join(lines)
    messages = [{"role": "system", "content": SCRIPT_DIRECTOR_SYSTEM}, {"role": "user", "content": facts}]
    result = await _json_call(llm, messages, ScriptBoard, temperature=0.7, max_tokens=4000)
    got, known = result.value.scenes, {c["id"]: len(c["focus"]) for c in captures}
    scenes = []
    for i, beat in enumerate(beats):
        made = got[i] if i < len(got) else ScriptScene()
        kind_of = beat.type or made.type
        if kind_of == "screen" and made.capture not in known:
            kind_of = "motion"
        motion = made.motion
        if kind_of == "motion" and beat.style:
            motion = (motion or Motion()).model_copy(update={"style": beat.style})
        scenes.append(Scene(type=kind_of, seconds=beat.seconds, caption=made.caption, voice=beat.words, text=made.text,
                            capture=made.capture if kind_of == "screen" else "",
                            focus=min(made.focus, max(0, known.get(made.capture, 1) - 1)), motion=motion))
    board = Storyboard(kind=kind, source="script", structure="guion", look=random.choice(LOOKS), title=result.value.title,
                       post=result.value.post, music=music, scenes=scenes)
    result.value = tidy_storyboard(board)
    return result


class Voices(BaseModel):
    voices: list[Annotated[str, _clip(300)]]


def overlong(board: Storyboard) -> list[str]:
    """The scenes whose voice does not fit their seconds, said for the director."""
    return [f"escena {i + 1} ({s.seconds:g} s): {n} palabras, máximo {int(s.seconds * WORDS_PER_SECOND)}"
            for i, s in enumerate(board.scenes) if (n := len(s.voice.split())) > s.seconds * WORDS_PER_SECOND + 1]
