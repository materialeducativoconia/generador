"""The Casting director: the recurring characters of a picture book, drawn the same on every page.

Before the cover, the agent looks at the shared character library and either reuses a character as it is, derives
a new one from it (same proportions and style, a costume for this topic) or creates a new one. Each new character
gets a model sheet (turnaround and expressions) painted once; the sheet is the reference the cover and every plate
are painted from. Characters made for paid tomes join the library, so it grows with use and the next tome often
costs nothing extra. The design rules come from the benchmark in docs/character-benchmark.md.
"""

import asyncio
import json
import logging
import uuid
from typing import Annotated

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.agents import AgentResult, Brief, _json_call
from app.content import Design
from app.illustrator import NO_TEXT, normalize_subject, reference_image

log = logging.getLogger("casting")

CAST_GENRES = ("picture_book", "story_book", "coloring_book")  # books with a guide on every page
SHEET_STYLE = ("premium children's book illustration, warm gouache and coloured-pencil texture, soft shading, "
               "clean readable shapes")
Hex = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


class CastMember(BaseModel):
    reuse: str | None = None      # a library character's id, used exactly as it is
    based_on: str | None = None   # a library character's id this new one derives from
    name: str = Field(min_length=1, max_length=40)
    role: str = "guide"           # guide | companion
    archetype: str = Field(min_length=3, max_length=80)
    look: str = Field(min_length=10, max_length=600)
    personality: str = Field(default="", max_length=300)
    signature: str = Field(default="", max_length=120)
    palette: list[Hex] = Field(default_factory=list, max_length=4)


class Casting(BaseModel):
    cast: list[CastMember] = Field(min_length=1, max_length=2)
    reason: str = ""


CASTING_SYSTEM = """Eres directora de casting de personajes de una editorial de libros educativos infantiles premium
(al nivel de Larousse «Mi primer ¡Dime!», Oxford Reading Tree, Usborne o DK). Eliges el personaje guía del tomo
y, si ayuda, un compañero. Responde solo con json:
{"cast": [{"reuse": "id de la biblioteca o null", "based_on": "id de la biblioteca o null", "name": "…",
  "role": "guide|companion", "archetype": "en español, 2 a 5 palabras", "look": "en inglés: aspecto fijo",
  "personality": "en español, una frase", "signature": "en inglés: el detalle que nunca falta",
  "palette": ["#hex", "#hex", "#hex"]}], "reason": "una frase"}

Primero la biblioteca:
- Si un personaje de la biblioteca encaja con el tema y el público, reutilízalo: "reuse" con su id y copia sus
  datos tal cual. Es lo mejor: el lector reconoce al personaje entre tomos y no cuesta nada.
- Si casi encaja, crea uno derivado: "based_on" con su id, mismo cuerpo, cara y proporciones, con ropa o
  accesorios para este tema (p. ej. el mismo niño con traje de astronauta). Nombre propio nuevo solo si es otro
  personaje; si es el mismo con otro traje, conserva el nombre.
- Si nada encaja, crea uno nuevo (reuse y based_on en null).

Reglas de diseño (lo que hacen las editoriales premium):
- Un guía de la edad del lector o un poco mayor (el niño se ve en él), curioso y amable; o un animal o
  criatura simpática ligada al tema. Un compañero opcional (mascota, robot, animalito) da ternura y humor.
- Silueta legible: reconocible solo por su contorno; formas redondas y amables; cabeza grande (proporción
  cabeza:cuerpo de 1:3 a 1:4) y ojos expresivos.
- Máximo 3 colores de identidad saturados, fijos, que contrasten con los fondos; da sus hex en "palette".
- Un rasgo de firma que siempre está (bufanda amarilla, lentes redondos, gorra naranja, una mancha en la oreja).
- Ropa simple y sin logos, letras ni números; nada de detalles finos que cambien de página a página.
- Diversidad real y respetuosa (tono de piel, cabello, discapacidad) sin estereotipos; varía respecto a los
  personajes más usados de la biblioteca cuando crees uno nuevo.
- "look" en inglés, 40 a 90 palabras, concreto y repetible: especie o edad, piel, cabello (forma y color),
  ojos, ropa pieza por pieza con colores, accesorios, proporciones. Nada de poses ni escenas.
- Respeta la regla de personajes del pedido: sin personajes de películas o marcas salvo que se permitan; una
  mascota de la línea editorial indicada es obligatoria como guía.
- Libros para colorear: diseño de contorno claro, sin texturas ni degradados que dependan del color."""


async def casting_director(llm, brief: Brief, title: str, design: Design | None,
                           library: list[dict]) -> AgentResult[Casting]:
    shelf = "\n".join(
        f"- id {c['id']} | {c['name']} | {c['archetype']} | usado {c['use_count']} veces | temas: "
        f"{', '.join(c['topics'][:6]) or '—'} | {c['look']}" for c in library) or "(vacía)"
    mascot = design.brand.mascot if design and design.brand and design.brand.mascot else None
    extra = f"\nMascota de la línea editorial (úsala como guía, con este nombre): {mascot.name}: {mascot.look}" \
        if mascot else ""
    messages = [
        {"role": "system", "content": CASTING_SYSTEM},
        {"role": "user", "content": f"Título: {title}\n{brief.describe()}{extra}\nBiblioteca de personajes:\n{shelf}"},
    ]
    result = await _json_call(llm, messages, Casting, temperature=0.7, max_tokens=2500)
    known = {str(c["id"]) for c in library}
    for m in result.value.cast:  # an id the model made up is a new character, not a reuse
        m.reuse = m.reuse if m.reuse in known else None
        m.based_on = m.based_on if m.based_on in known else None
    return result


def sheet_prompt(m: CastMember | dict, style: str, derived: bool) -> str:
    get = m.get if isinstance(m, dict) else lambda k: getattr(m, k)
    base = ("The attached image is the model sheet of the character this one is based on: keep exactly the same "
            "body, face, proportions and drawing style, change only what the description changes. ") if derived else ""
    return (f"{base}Character model sheet for a children's book, one character only: {get('name')}, "
            f"{get('look')} Signature detail always visible: {get('signature') or 'as described'}. "
            f"Top row: full body turnaround, front view, three-quarter view, side view and back view, standing in a "
            f"neutral pose, same size and evenly spaced. Bottom row: four head close-ups with different expressions "
            f"(happy, surprised, thinking, proud). Art style: {style}. Identity colours: "
            f"{', '.join(get('palette') or []) or 'as described'}. Plain pure white background, no scenery, no props "
            f"other than the character's own accessories, soft even light. {NO_TEXT}")


async def library_for(conn, user_id, topic: str, limit: int = 12) -> list[dict]:
    rows = (await conn.execute(text(
        """select id::text, name, role, archetype, look, personality, signature, palette, topics, sheet_key,
                  use_count, style
             from public.characters
            where sheet_key is not null and status = 'ready' and (shared or user_id = :u)
            order by greatest(extensions.similarity(array_to_string(topics, ' '), :t),
                              extensions.similarity(archetype, :t)) desc, use_count desc, created_at
            limit :n"""), {"u": user_id, "t": topic, "n": limit})).mappings().all()
    return [dict(r) for r in rows]


async def cast_tome(deps, job: dict, series, design: Design | None, brief: Brief, *, paint: bool) -> tuple[list[dict], float]:
    """The tome's cast, chosen once and kept on the series. `paint` False (a free preview): library characters
    only, no new sheet. Returns the cast and what painting new sheets cost."""
    from app.jobs import _insert_logs, _json  # jobs imports this module

    if series["cast"] is not None:
        cast = _json(series["cast"])
        if any(c.get("restyle") for c in cast):  # another version of a tome, in another style
            return await _restyle_cast(deps, job, cast, design, paint=paint)
        return cast, 0.0
    if (series["genre"] or "") not in CAST_GENRES:
        return [], 0.0
    topic = normalize_subject(series["title"] or series["topic"])
    house = design.house_style if design else None
    if series.get("guide_id"):  # the user picked the guide: no casting call
        async with deps.engine.begin() as conn:
            row = (await conn.execute(text(
                """update public.characters set use_count = use_count + 1 where id = :id and status = 'ready'
                   returning id::text, name, role, archetype, look, signature, sheet_key"""),
                {"id": series["guide_id"]})).mappings().first()
        if row:
            key, cost = await styled_sheet(deps, dict(row), house, design, paint=paint)
            cast = [_entry(row["id"], row, key)]
            async with deps.engine.begin() as conn:
                await conn.execute(text('update public.series set "cast" = cast(:c as jsonb) where id = :s'),
                                   {"s": job["series_id"], "c": json.dumps(cast)})
            return cast, cost
    async with deps.engine.connect() as conn:
        library = await library_for(conn, job["user_id"], topic)
    try:
        result = await casting_director(deps.llm, brief, series["title"] or series["topic"], design, library)
    except Exception as exc:  # the cast is a quality step: without it the Art director invents the guide
        log.warning("casting failed for %s: %s", job["series_id"], exc)
        return [], 0.0
    by_id = {c["id"]: c for c in library}
    mascot = bool(design and design.brand and design.brand.mascot)
    private = mascot or brief.brand_characters  # a brand's mascot or a licensed character is never lent out
    style = (design.art_style if design and design.art_style else SHEET_STYLE)
    cast, cost = [], 0.0
    for m in result.value.cast:
        if m.reuse:
            row = by_id[m.reuse]
            async with deps.engine.begin() as conn:
                await conn.execute(text(
                    """update public.characters set use_count = use_count + 1,
                              topics = (select array_agg(distinct t) from unnest(topics || array[:t]) t)
                        where id = :id"""), {"id": m.reuse, "t": topic})
            key, restyled = await styled_sheet(deps, row, house, design, paint=paint)
            cost += restyled
            cast.append(_entry(row["id"], row, key))
            continue
        if not paint or deps.images is None:
            cast.append(_entry(None, m.model_dump(), None))
            continue
        parent = by_id.get(m.based_on) if m.based_on else None
        refs = []
        if parent:
            try:
                refs = [reference_image(await deps.storage.download(parent["sheet_key"], bucket="images"))]
            except Exception:
                log.warning("sheet %s unavailable", parent["sheet_key"])
        try:
            image = await deps.images.generate(sheet_prompt(m, style, bool(refs)), references=refs,
                                               aspect_ratio="4:3", resolution="2K")
        except Exception as exc:
            log.warning("model sheet failed for %s: %s", m.name, exc)
            cast.append(_entry(None, m.model_dump(), None))
            continue
        cost += image.cost_usd or 0
        char_id = str(uuid.uuid4())
        key = f"characters/{char_id}.jpg"
        await deps.storage.upload(key, await asyncio.to_thread(_jpeg, image.data), "image/jpeg", bucket="images")
        async with deps.engine.begin() as conn:
            await conn.execute(text(
                """insert into public.characters (id, name, role, archetype, look, personality, signature, palette,
                          style, topics, audience, sheet_key, based_on, user_id, shared, use_count)
                   values (:id, :name, :role, :arch, :look, :pers, :sig, :pal, :style, array[:t], :aud, :key,
                           :parent, :u, :shared, 1)"""),
                {"id": char_id, "name": m.name, "role": m.role if m.role in ("guide", "companion") else "guide",
                 "arch": m.archetype, "look": m.look, "pers": m.personality, "sig": m.signature, "pal": m.palette,
                 "style": style, "t": topic, "aud": brief.audience, "key": key,
                 "parent": parent["id"] if parent else None, "u": job["user_id"],
                 "shared": not private and not series["preview"]})
            if house:
                await conn.execute(text(
                    "insert into public.character_sheets (character_id, style, sheet_key) values (:id, :st, :k)"),
                    {"id": char_id, "st": house, "k": key})
        cast.append(_entry(char_id, m.model_dump(), key))
    async with deps.engine.begin() as conn:
        await _insert_logs(conn, job, "casting", result.attempts)
        await conn.execute(text('update public.series set "cast" = cast(:c as jsonb) where id = :s'),
                           {"s": job["series_id"], "c": json.dumps(cast)})
    return cast, cost


RESTYLE = ("The attached image is this character's model sheet: draw exactly the same character (face, hair, "
           "outfit, colours, proportions, signature detail) in the new art style below, same layout. ")



async def _restyle_cast(deps, job: dict, cast: list[dict], design: Design | None, *, paint: bool) -> tuple[list[dict], float]:
    """The cast a tome's new version kept, each one redrawn in the version's house style (or found already drawn)."""
    house = design.house_style if design else None
    cost = 0.0
    for c in cast:
        if not c.pop("restyle", False) or not c.get("character_id"):
            continue
        async with deps.engine.connect() as conn:
            row = (await conn.execute(text(
                "select id::text, name, role, archetype, look, signature, sheet_key from public.characters where id = :id"),
                {"id": c["character_id"]})).mappings().first()
        if row:
            c["sheet_key"], spent = await styled_sheet(deps, dict(row), house, design, paint=paint)
            cost += spent
    async with deps.engine.begin() as conn:
        await conn.execute(text('update public.series set "cast" = cast(:c as jsonb) where id = :s'),
                           {"s": job["series_id"], "c": json.dumps(cast)})
    return cast, cost


async def styled_sheet(deps, row: dict, house: str | None, design: Design | None, *,
                       paint: bool) -> tuple[str | None, float]:
    """The character's sheet in the tome's house style: kept from an earlier tome, or redrawn from its own sheet
    once (paint False: the sheet it has). Returns the sheet key and what redrawing cost."""
    if not house or not row.get("sheet_key"):
        return row.get("sheet_key"), 0.0
    async with deps.engine.connect() as conn:
        kept = (await conn.execute(text(
            "select sheet_key from public.character_sheets where character_id = :id and style = :st"),
            {"id": row["id"], "st": house})).scalar_one_or_none()
    if kept or not paint or deps.images is None:
        return kept or row["sheet_key"], 0.0
    try:
        base = reference_image(await deps.storage.download(row["sheet_key"], bucket="images"))
        image = await deps.images.generate(RESTYLE + sheet_prompt(row, design.art_style or SHEET_STYLE, False),
                                           references=[base], aspect_ratio="4:3", resolution="2K")
    except Exception as exc:  # the base sheet still keeps the character recognisable
        log.warning("restyle of %s failed: %s", row["name"], exc)
        return row["sheet_key"], 0.0
    key = f"characters/{row['id']}-{house}.jpg"
    await deps.storage.upload(key, await asyncio.to_thread(_jpeg, image.data), "image/jpeg", bucket="images")
    async with deps.engine.begin() as conn:
        await conn.execute(text(
            """insert into public.character_sheets (character_id, style, sheet_key) values (:id, :st, :k)
               on conflict (character_id, style) do update set sheet_key = excluded.sheet_key"""),
            {"id": row["id"], "st": house, "k": key})
    return key, image.cost_usd or 0.0


MAKER_SYSTEM = """Eres diseñadora de personajes de una editorial de libros educativos infantiles premium (al nivel de
Larousse, Usborne, Oxford Reading Tree o DK). Conviertes la descripción del usuario en un personaje recurrente que
se pueda dibujar igual en cada página. Responde solo con json:
{"name": "…", "role": "guide|companion", "archetype": "en español, 2 a 5 palabras",
 "look": "en inglés: aspecto fijo", "personality": "en español, una frase",
 "signature": "en inglés: el detalle que nunca falta", "palette": ["#hex", "#hex", "#hex"]}

- Respeta lo que pide el usuario (especie, edad, ropa, nombre si lo da); completa lo que falte con oficio.
- Silueta legible y formas amables; cabeza grande (1:3 a 1:4) y ojos expresivos; máximo 3 colores de identidad.
- Un rasgo de firma que siempre está. Ropa simple, sin logos, letras ni números.
- "look" en inglés, 40 a 90 palabras, concreto y repetible: especie o edad, piel, cabello, ojos, ropa pieza por
  pieza con colores, accesorios, proporciones. Nada de poses ni escenas.
- Nunca copies personajes de películas, series, videojuegos o marcas: crea uno original del mismo espíritu.
- Si hay un personaje base, conserva su cuerpo, cara y proporciones y cambia solo lo que pide el usuario."""


async def character_designer(llm, description: str, parent: dict | None) -> AgentResult[CastMember]:
    base = (f"\nPersonaje base: {parent['name']} | {parent['archetype']} | {parent['look']} | firma: "
            f"{parent['signature']}") if parent else ""
    messages = [{"role": "system", "content": MAKER_SYSTEM},
                {"role": "user", "content": f"Descripción del usuario: {description}{base}"}]
    return await _json_call(llm, messages, CastMember, temperature=0.7, max_tokens=1200)


async def make_character(deps, job: dict) -> None:
    """The character job: the designer writes the character, the Illustrator paints its sheet in the chosen style."""
    from app.house_styles import BY_KEY, NOT_AI
    from app.jobs import JobFailed, _insert_logs, _succeed  # jobs imports this module

    char_id = job["payload"]["character_id"]
    async with deps.engine.connect() as conn:
        row = (await conn.execute(text("select * from public.characters where id = :id"),
                                  {"id": char_id})).mappings().one_or_none()
        parent = (await conn.execute(text(
            "select id::text, name, archetype, look, signature, sheet_key from public.characters where id = :id"),
            {"id": row["based_on"]})).mappings().one_or_none() if row and row["based_on"] else None
    if row is None:  # deleted meanwhile
        async with deps.engine.begin() as conn:
            await _succeed(conn, job)
        return
    if deps.images is None:
        raise JobFailed("not_configured", "Falta OPENROUTER_API_KEY para pintar personajes.")
    result = await character_designer(deps.llm, row["description"] or row["name"], dict(parent) if parent else None)
    m = result.value
    house = job["payload"].get("style")
    style = f"{BY_KEY[house].prompt} {NOT_AI}" if house in BY_KEY else SHEET_STYLE
    refs = []
    if parent and parent["sheet_key"]:
        try:
            refs = [reference_image(await deps.storage.download(parent["sheet_key"], bucket="images"))]
        except Exception:
            log.warning("sheet %s unavailable", parent["sheet_key"])
    image = await deps.images.generate(sheet_prompt(m, style, bool(refs)), references=refs, aspect_ratio="4:3",
                                       resolution="2K")
    key = f"characters/{char_id}.jpg"
    await deps.storage.upload(key, await asyncio.to_thread(_jpeg, image.data), "image/jpeg", bucket="images")
    async with deps.engine.begin() as conn:
        await _insert_logs(conn, job, "character", result.attempts)
        await conn.execute(text(
            """update public.characters set name = :name, role = :role, archetype = :arch, look = :look,
                      personality = :pers, signature = :sig, palette = :pal, style = :style, sheet_key = :key,
                      status = 'ready', error = null where id = :id"""),
            {"id": char_id, "name": m.name, "role": m.role if m.role in ("guide", "companion") else "guide",
             "arch": m.archetype, "look": m.look, "pers": m.personality, "sig": m.signature, "pal": m.palette,
             "style": style, "key": key})
        if house in BY_KEY:
            await conn.execute(text(
                """insert into public.character_sheets (character_id, style, sheet_key) values (:id, :st, :k)
                   on conflict (character_id, style) do update set sheet_key = excluded.sheet_key"""),
                {"id": char_id, "st": house, "k": key})
        await _succeed(conn, job)


def _entry(char_id, data: dict, sheet_key) -> dict:
    return {"character_id": char_id, "name": data["name"], "role": data.get("role") or "guide",
            "archetype": data.get("archetype") or "", "look": data["look"], "signature": data.get("signature") or "",
            "sheet_key": sheet_key}


async def cast_sheets(deps, cast: list[dict]) -> list[bytes]:
    """The cast's model sheets, ready to attach as references (a missing one is skipped)."""
    out = []
    for c in cast:
        if c.get("sheet_key"):
            try:
                out.append(reference_image(await deps.storage.download(c["sheet_key"], bucket="images")))
            except Exception:
                log.warning("sheet %s unavailable", c["sheet_key"])
    return out


def cast_line(cast: list[dict]) -> str:
    return "; ".join(f"{c['name']}: {c['look']}" + (f" Always: {c['signature']}." if c.get("signature") else "")
                     for c in cast)


def _jpeg(data: bytes) -> bytes:
    import io

    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue()


# Starter characters the worker paints once, so the first tomes already find a cast in the library.
SEED = [
    dict(name="Lía", role="guide", archetype="niña exploradora", palette=["#F2B705", "#2E7D6B", "#E4572E"],
         signature="a mustard-yellow explorer vest with two big pockets",
         personality="Curiosa y valiente; siempre pregunta «¿por qué?».",
         look="A 6-year-old Latina girl with warm light-brown skin, big dark-brown eyes, thick black hair in two "
              "puffy pigtails tied with red bands, a mustard-yellow explorer vest with two big pockets over a white "
              "t-shirt, teal shorts, red sneakers with white soles, a small brown backpack. Round friendly face, "
              "head-to-body ratio about 1:3."),
    dict(name="Mateo", role="guide", archetype="niño curioso con lentes", palette=["#3A7BD5", "#7CB342", "#FF8F00"],
         signature="big round orange glasses",
         personality="Observador y ordenado; le encanta medir y comparar.",
         look="A 7-year-old boy with fair skin and freckles, short wavy chestnut hair with a cowlick, big round "
              "orange glasses, a blue hoodie with green cuffs, khaki trousers rolled at the ankle, green sneakers. "
              "Slim build, round head, head-to-body ratio about 1:3.5."),
    dict(name="Zuri", role="guide", archetype="niña científica", palette=["#8E44AD", "#16A085", "#F1C40F"],
         signature="purple safety goggles pushed up on her forehead",
         personality="Inventiva y alegre; convierte todo en un experimento.",
         look="An 8-year-old Afro-Latina girl with deep brown skin, a big round afro of black curls, purple safety "
              "goggles pushed up on her forehead, a short white lab coat over a teal dress, yellow leggings, purple "
              "boots. Bright wide smile, head-to-body ratio about 1:3.5."),
    dict(name="Iker", role="guide", archetype="niño deportista en silla de ruedas", palette=["#FF7A00", "#1565C0", "#43A047"],
         signature="an orange cap worn backwards",
         personality="Rápido, bromista y buen compañero de equipo.",
         look="A 7-year-old Indigenous Mexican boy with tan skin, straight black hair, dark eyes, an orange cap worn "
              "backwards, a blue t-shirt, green shorts, in a light sporty wheelchair with blue wheels. Cheerful, "
              "head-to-body ratio about 1:3."),
    dict(name="Profe Búho", role="guide", archetype="búho sabio maestro", palette=["#8D6E63", "#D32F2F", "#FFCA28"],
         signature="a long red knitted scarf",
         personality="Paciente y sabio; explica con calma y buen humor.",
         look="A round, friendly brown owl with cream belly feathers, big amber eyes behind small gold half-moon "
              "glasses, short tufted ears, a long red knitted scarf, small yellow feet. Plump egg-shaped body, very "
              "simple feather shapes."),
    dict(name="Pipo", role="companion", archetype="perrito compañero", palette=["#FFFFFF", "#8D5524", "#1E88E5"],
         signature="a blue neckerchief and a brown patch over the left eye",
         personality="Juguetón y leal; siempre encuentra algo.",
         look="A small fluffy white puppy with floppy ears, a brown patch over the left eye, a black button nose, a "
              "short wagging tail, a blue neckerchief. Round body, short legs, big head."),
    dict(name="Chispa", role="companion", archetype="robot amigable", palette=["#26C6DA", "#FFB300", "#ECEFF1"],
         signature="a light-bulb antenna that glows yellow",
         personality="Entusiasta; se ilumina cuando aprende algo.",
         look="A small round turquoise robot the size of a cat, a glossy dome head with a dark screen face showing "
              "two oval eyes and a smile, a light-bulb antenna glowing yellow, stubby arms with round hands, floats "
              "on a small hover base. Simple rounded shapes."),
    dict(name="Kiki", role="companion", archetype="patito escondido", palette=["#FFD600", "#FF6D00", "#FFFFFF"],
         signature="tiny, always hidden somewhere in the picture",
         personality="Tímido; se esconde en cada página para que lo encuentres.",
         look="A tiny round yellow duckling with an orange beak and feet, small black dot eyes and a little tuft of "
              "feathers on the head. Extremely simple shape so it stays recognisable when very small."),
]

PAUSE_SECONDS = 75


async def keep_seeded(engine, images, storage) -> None:
    """The worker's background task: the starter characters and their sheets, painted once (8 × ~$0.07)."""
    for c in SEED:
        async with engine.begin() as conn:
            row = (await conn.execute(text("select id, sheet_key from public.characters where seed and name = :n"),
                                      {"n": c["name"]})).one_or_none()
        if row and row.sheet_key:
            continue
        try:
            image = await images.generate(sheet_prompt(c, SHEET_STYLE, False), aspect_ratio="4:3", resolution="2K")
        except Exception as exc:
            log.warning("seed sheet %s failed: %s", c["name"], exc)
            await asyncio.sleep(PAUSE_SECONDS)
            continue
        char_id = str(row.id) if row else str(uuid.uuid4())
        key = f"characters/{char_id}.jpg"
        await storage.upload(key, await asyncio.to_thread(_jpeg, image.data), "image/jpeg", bucket="images")
        async with engine.begin() as conn:
            await conn.execute(text(
                """insert into public.characters (id, name, role, archetype, look, personality, signature, palette,
                          style, sheet_key, shared, seed)
                   values (:id, :name, :role, :archetype, :look, :personality, :signature, :palette, :style, :key,
                           true, true)
                   on conflict (id) do update set sheet_key = excluded.sheet_key"""),
                {"id": char_id, **c, "style": SHEET_STYLE, "key": key})
        log.info("seeded character %s", c["name"])
        await asyncio.sleep(PAUSE_SECONDS)
