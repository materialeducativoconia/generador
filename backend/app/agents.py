"""Phase-1 agents: the Architect plans the tome, the Writer fills one section.

Each agent is a bounded step: fixed prompt, JSON output validated with Pydantic, and at most
one repair round where the validation error goes back to the model.
"""

import json
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.content import Outline, SectionContent
from app.llm import LLM, Completion

T = TypeVar("T", bound=BaseModel)

PROMPT_VERSION = {"architect": "architect@1", "writer": "writer@1"}


@dataclass
class Brief:
    request: str
    audience: str
    language: str = "es"
    section_count: int | None = None  # None: the Architect decides
    extra_instructions: str | None = None

    def describe(self) -> str:
        lines = [f"Pedido del usuario: {self.request}", f"Público: {self.audience}", f"Idioma: {self.language}"]
        lines.append(f"Número de secciones: {self.section_count}" if self.section_count
                     else "Número de secciones: decide tú (entre 1 y 20) según el pedido")
        if self.extra_instructions:
            lines.append(f"Instrucciones extra: {self.extra_instructions}")
        return "\n".join(lines)


@dataclass
class Attempt:
    outcome: str  # ok | invalid_output | truncated
    messages: list[dict]
    completion: Completion
    error: str | None = None


@dataclass
class AgentResult(Generic[T]):
    value: T
    attempts: list[Attempt] = field(default_factory=list)


class AgentFailed(Exception):
    def __init__(self, code: str, message: str, attempts: list[Attempt]):
        super().__init__(message)
        self.code = code
        self.attempts = attempts


ARCHITECT_SYSTEM = """Eres el Arquitecto de un generador de material educativo imprimible.
Recibes el pedido de un usuario (puede ser cualquier cosa: un libro de colorear de preescolar, un cuadernillo
de fichas de lectoescritura, un método de piano para principiantes, una serie de lecciones de ciencias…) y
diseñas el TOMO completo.

1. Elige el género:
   - "coloring_book": libro de colorear; cada sección es una página con un dibujo de línea a página completa.
   - "worksheets": cuadernillo de fichas de actividades (repasar, colorear, unir, recortar, completar).
   - "tutorial": método o guía paso a paso para aprender una habilidad (instrumento, oficio, software…).
   - "lesson_series": secuencia didáctica de lecciones para docentes.
2. Divide el tomo en secciones coherentes y progresivas (de lo simple a lo complejo).
3. Para cada sección da un título claro, de 1 a 4 objetivos y de 1 a 8 puntos clave (conceptos, palabras,
   dibujos o ejercicios que la sección debe incluir).

Responde SOLO con un objeto json con esta forma:
{"title": "…", "genre": "coloring_book|worksheets|tutorial|lesson_series", "style_notes": "tono y estilo visual",
 "sections": [{"title": "…", "objectives": ["…"], "key_points": ["…"]}]}"""

WRITER_SYSTEM = """Eres el Redactor de un generador de material educativo imprimible. Escribes UNA sección del tomo
como una lista de bloques de página. No escribas HTML ni Markdown: solo **negrita** y *cursiva* dentro del texto.

Catálogo de bloques (usa solo estos "type"):
- heading {level: 2|3, text}
- paragraph {text}
- list {style: bullet|number|check, items: [..]}
- callout {variant: key_idea|tip|warning|fun_fact, title?, text}
- table {caption?, headers: [..], rows: [[..]]}
- example {title?, text}
- activity {title, duration_minutes?, materials: [..], steps: [..]}
- exercise {kind: open|multiple_choice|true_false|fill_blank, prompt, options?: [..], answer, explanation?,
  answer_space_lines?}
- keyboard {start: "C4", octaves: 1-3, highlight: ["C4","E4"], caption?}  ← teclado de piano dibujado por código
- tracing {text, repeat, instruction?}  ← letras/sílabas punteadas para repasar
- letter_grid {targets: ["A","a"], distractors: [..], rows, cols, instruction?}  ← círculos para colorear
- image {kind: line_art|illustration|photo|diagram, subject, caption?, size: full|half|small}
  ← describe qué dibujar; un ilustrador lo hará después. Para colorear usa line_art.
- writing_lines {lines, label?}
- page_break {}

Reglas según el género:
- coloring_book: un heading con el título y un image line_art size "full" por página; texto mínimo.
- worksheets: cada ficha empieza con heading "Ficha N"; instrucciones cortas para niños; usa tracing,
  letter_grid, image line_art, writing_lines y exercise; separa fichas con page_break.
- tutorial: explica paso a paso; usa keyboard, table, callout tip, activity y exercises de práctica.
- lesson_series: introducción, explicación, ejemplos, una activity y al menos 3 exercise con answer.
Cada bloque lleva un "id" único ("b1", "b2", …). Los ejercicios llevan "answer" (va al solucionario).

Responde SOLO con un objeto json: {"schema_version": 1, "summary": "…", "blocks": [ … ]}"""


async def architect(llm: LLM, brief: Brief) -> AgentResult[Outline]:
    messages = [
        {"role": "system", "content": ARCHITECT_SYSTEM},
        {"role": "user", "content": brief.describe()},
    ]
    result = await _json_call(llm, messages, Outline, temperature=0.7, max_tokens=4000)
    if brief.section_count and len(result.value.sections) != brief.section_count:
        result.value.sections = result.value.sections[: brief.section_count]
    return result


async def writer(llm: LLM, brief: Brief, outline: Outline, position: int) -> AgentResult[SectionContent]:
    section = outline.sections[position - 1]
    # Most stable first, so DeepSeek's prefix cache covers everything but the last message.
    messages = [
        {"role": "system", "content": WRITER_SYSTEM},
        {"role": "user", "content": f"{brief.describe()}\n\nEsquema aprobado del tomo:\n"
                                    f"{outline.model_dump_json(indent=1)}"},
        {"role": "user", "content": f"Escribe ahora la sección {position}: {section.title}\n"
                                    f"Objetivos: {'; '.join(section.objectives)}\n"
                                    f"Puntos clave: {'; '.join(section.key_points)}"},
    ]
    return await _json_call(llm, messages, SectionContent, temperature=1.0, max_tokens=8000)


async def _json_call(llm: LLM, messages: list[dict], model: type[T], *, temperature: float,
                     max_tokens: int) -> AgentResult[T]:
    attempts: list[Attempt] = []
    for round_ in range(2):
        completion = await llm.complete(messages, temperature=temperature, max_tokens=max_tokens)
        if completion.finish_reason == "length":
            attempts.append(Attempt("truncated", messages, completion, "salida truncada"))
            raise AgentFailed("too_long", "La respuesta del modelo se cortó por larga.", attempts)
        try:
            value = model.model_validate(json.loads(completion.text))
        except (json.JSONDecodeError, ValidationError) as exc:
            error = str(exc)[:2000]
            attempts.append(Attempt("invalid_output", messages, completion, error))
            messages = [*messages, {"role": "assistant", "content": completion.text},
                        {"role": "user", "content": f"Tu respuesta no es válida:\n{error}\n"
                                                    "Corrígela y responde solo con el json completo."}]
            continue
        attempts.append(Attempt("ok", messages, completion))
        return AgentResult(value, attempts)
    raise AgentFailed("invalid_output", "El modelo devolvió contenido inválido dos veces.", attempts)
