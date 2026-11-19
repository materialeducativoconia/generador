"""«Escena a medida»: Claude (OpenRouter) writes one scene of a marketing video as a Remotion component, the way
Claude Code writes a video from a prompt. The browser compiles it and draws it; a scene that does not compile or
throws falls back to its template, so a video never breaks."""

import json
import re

import httpx

from app.llm import UpstreamAuthError, UpstreamError

MAX_CODE = 24000

SYSTEM = """Eres un motion designer senior que programa escenas de video en React con Remotion, como las de los mejores
anuncios de apps (Apple, Linear, Duolingo): composición limpia, tipografía grande, movimiento con intención,
curvas suaves (spring o Easing.bezier), ritmo que acompaña la voz y nada estático más de medio segundo.

Escribe UNA escena de un video de Jelyx (la app que convierte un tema de clase en un libro ilustrado en PDF para
docentes). Devuelve solo el código, en un bloque ```jsx, que define:

function Scene({ frame, fps, dur, width, height, look, caption, voice, text, title, book, step }) { ... }

- frame: el fotograma actual dentro de la escena (0 … dur-1), a {fps} fps. dur: la duración en fotogramas.
- width, height: el lienzo en px ({width}×{height}). Mide todo en proporción (p. ej. width * 0.08), nunca px fijos.
- look: { bg, ink, accent }: el fondo, el color del texto y el acento de la marca. Úsalos como base.
- caption: el texto en pantalla (puede ir vacío); voice: lo que dice la voz en off mientras tanto; text: un dato extra.
- title: el título del video; book: el título del libro que muestra; step: número de paso o null.

Tienes en el ámbito, sin importar nada: React, AbsoluteFill, interpolate, spring, Easing, random (random('semilla')
da un número 0..1 estable: nunca Math.random), Icon ({ name, size, color, stroke }: iconos de línea; name uno de
{icons}) y FONT (la tipografía de la marca, ya aplicada).

Reglas que no se rompen:
- Todo el movimiento sale de frame: nada de CSS animation/transition, setTimeout, useEffect ni estado.
- Solo divs, spans y SVG inline (path, circle, rect, line, polygon, g, linearGradient). Sin img, video, canvas,
  iframe, fetch, window, document, eval, import ni require.
- Estilos con transform, opacity, background (colores y gradientes), border, borderRadius, boxShadow, clipPath.
  Sin filter: blur, backdropFilter ni 3D (perspective, rotateX/rotateY, translateZ): el render del MP4 no los pinta.
- La escena entra animada en sus primeros ~12 fotogramas y se desvanece en los últimos 10.
- El texto se lee: grande, con contraste, dentro de un margen del 7 % del lienzo, en español tal como viene.
- El código cabe en {max} caracteres. Nada de comentarios largos."""

USER = """Video: «{title}» · libro: «{book}» · colores: fondo {bg}, texto {ink}, acento {accent}.
Escenas del video (la tuya marcada con ▶):
{outline}

Tu escena dura {seconds} s ({dur} fotogramas).
Texto en pantalla: «{caption}»
Voz en off: «{voice}»
{extra}
Diseña algo que explique visualmente lo que dice la voz, no solo el texto: metáforas, diagramas, iconos que se
conectan, números que cuentan, objetos que se transforman. Que se sienta premium y distinto de las demás escenas."""

CHANGE = """Este es el código actual de la escena:
```jsx
{code}
```
Cámbialo así: {change}
Devuelve la escena completa."""

FIX = "Ese código no se puede usar: {why}. Corrígelo y devuelve la escena completa en un bloque ```jsx."

FORBIDDEN = [(r"\bimport\b|\brequire\s*\(", "usa import o require"), (r"\bfetch\s*\(|XMLHttpRequest|WebSocket", "pide datos a la red"),
             (r"\beval\s*\(|\bnew\s+Function\b|\bFunction\s*\(", "usa eval o Function"),
             (r"\bwindow\b|\bdocument\b|\bglobalThis\b|localStorage|sessionStorage|\bcookie\b", "toca el navegador"),
             (r"<\s*(img|video|iframe|script|canvas|audio|object|embed)\b", "usa una etiqueta que no está permitida"),
             (r"dangerouslySetInnerHTML", "inyecta HTML"), (r"Math\.random", "usa Math.random en vez de random()"),
             (r"\buse(State|Effect|LayoutEffect|Ref)\b|setTimeout|setInterval|requestAnimationFrame", "anima fuera de frame")]


def problem(code: str) -> str | None:
    """Why the code cannot be drawn, or None."""
    if not code:
        return "no hay un bloque de código"
    if len(code) > MAX_CODE:
        return f"pasa de {MAX_CODE} caracteres"
    if not re.search(r"function\s+Scene\s*\(", code):
        return "no define function Scene(...)"
    for pattern, why in FORBIDDEN:
        if re.search(pattern, code):
            return why
    return None


def extract(text: str) -> str:
    """The scene's code from the reply: its ```jsx block, or the whole reply if it is only code."""
    blocks = re.findall(r"```(?:jsx|tsx|js|javascript|typescript)?\s*\n(.*?)```", text, flags=re.S)
    code = max(blocks, key=len) if blocks else text
    return code.strip()


class SceneCoder:
    def __init__(self, api_key: str, models: list[str], timeout: float = 180, transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key
        self.models = models
        self.timeout = timeout
        self.transport = transport

    async def write(self, model: str, messages: list[dict]) -> tuple[str, float]:
        """The scene's code (checked; one more try with the reason when it breaks a rule) and what it cost."""
        cost = 0.0
        for attempt in range(2):
            reply, spent = await self._ask(model, messages)
            cost += spent
            code = extract(reply)
            why = problem(code)
            if why is None:
                return code, round(cost, 4)
            messages = [*messages, {"role": "assistant", "content": reply}, {"role": "user", "content": FIX.format(why=why)}]
        raise UpstreamError("invalid_output", f"Claude no devolvió una escena válida ({why}).")

    async def _ask(self, model: str, messages: list[dict]) -> tuple[str, float]:
        body = {"model": model, "messages": messages, "temperature": 0.8, "max_tokens": 8000, "usage": {"include": True}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as http:
                response = await http.post("https://openrouter.ai/api/v1/chat/completions", json=body,
                                           headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.HTTPError as exc:
            raise UpstreamError("upstream_unavailable", "No se pudo conectar con Claude.") from exc
        if response.status_code in (401, 402, 403):
            raise UpstreamAuthError(f"OpenRouter {response.status_code}")
        if response.status_code >= 400:
            raise UpstreamError("upstream_unavailable", f"Claude respondió {response.status_code}.")
        payload = response.json()
        try:
            text = payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamError("invalid_output", f"Respuesta sin contenido: {json.dumps(payload)[:200]}") from exc
        return text, float((payload.get("usage") or {}).get("cost") or 0)


def label(model: str) -> str:
    """«anthropic/claude-opus-5.5» → «Claude Opus 5.5»."""
    name = model.split("/")[-1].replace("claude-", "")
    family, _, version = name.partition("-")
    return f"Claude {family.capitalize()} {version}".strip()


def fill(template: str, **values) -> str:
    """str.format for prompts that also show code with braces: only the named {keys} are replaced."""
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template
