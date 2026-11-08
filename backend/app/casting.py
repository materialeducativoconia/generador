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
    role: str = "guide"           # protagonist (a story's hero) | guide | companion
    archetype: str = Field(min_length=3, max_length=80)
    look: str = Field(min_length=10, max_length=600)
    personality: str = Field(default="", max_length=300)
    signature: str = Field(default="", max_length=120)
    palette: list[Hex] = Field(default_factory=list, max_length=4)


class Casting(BaseModel):
    cast: list[CastMember] = Field(min_length=1, max_length=2)
    reason: str = ""


class Extras(BaseModel):
    cast: list[CastMember] = Field(default_factory=list, max_length=2)  # only the characters the tome still lacks
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
- Libros para colorear: diseño de contorno claro, sin texturas ni degradados que dependan del color.
- Un personaje de la biblioteca sin nombre propio (su nombre es su arquetipo) se reutiliza con un nombre propio
  nuevo para este tomo."""

EXTRAS = """Este tomo ya tiene personajes, que no cambian. Devuelve en "cast" solo los personajes que nombra o pide el
usuario y todavía no están entre ellos (máximo 2; ninguno si ya están todos, "cast": []). Un nombre que ya está
en el reparto no es un personaje nuevo."""


STORY_CAST = """
Es un cuento: el primero del reparto es su PROTAGONISTA (role "protagonist"), quien vive la aventura de principio a
fin y sale en la portada: el personaje que nombra el título o el pedido; si no nombran a nadie, un niño o niña de la
edad del lector. Un guía sabio o un compañero, si hace falta, va después."""


async def casting_director(llm, brief: Brief, title: str, design: Design | None,
                           library: list[dict], kept: list[dict] | None = None,
                           genre: str = "") -> AgentResult[Casting | Extras]:
    shelf = "\n".join(
        f"- id {c['id']} | {c['name']} | {c['archetype']} | usado {c['use_count']} veces | temas: "
        f"{', '.join(c['topics'][:6]) or '—'} | {c['look']}" for c in library) or "(vacía)"
    mascot = design.brand.mascot if design and design.brand and design.brand.mascot else None
    extra = f"\nMascota de la línea editorial (úsala como guía, con este nombre): {mascot.name}: {mascot.look}" \
        if mascot else ""
    if genre == "story_book" and not kept:
        extra += STORY_CAST
    if kept:
        extra += "\nReparto de este tomo (ya dibujado):\n" + "\n".join(
            f"- {c['name']} | {c.get('archetype') or ''}" for c in kept)
    messages = [
        {"role": "system", "content": CASTING_SYSTEM + ("\n\n" + EXTRAS if kept else "")},
        {"role": "user", "content": f"Título: {title}\n{brief.describe()}{extra}\nBiblioteca de personajes:\n{shelf}"},
    ]
    result = await _json_call(llm, messages, Extras if kept else Casting, temperature=0.7, max_tokens=2500)
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
            f"(happy, surprised, thinking, proud). Every figure is the same single character with exactly one head "
            f"and one face (the side view shows one profile, the back view no face); no extra eyes, snouts, limbs "
            f"or tails. Art style: {style}. Identity colours: "
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

    kept = None
    if series["cast"] is not None:
        cast = _json(series["cast"])
        if not any(c.get("restyle") or c.get("extend") for c in cast):
            return cast, 0.0
        extend = bool([c.pop("extend") for c in cast if "extend" in c])
        cast, cost = await _restyle_cast(deps, job, cast, design, paint=paint)  # in another style: redrawn in it
        if not extend:
            return cast, cost
        kept = cast  # a new story or the next tome: the characters its request names are cast too
    if (series["genre"] or "") not in CAST_GENRES:
        return [], 0.0
    topic = normalize_subject(series["title"] or series["topic"])
    house = design.house_style if design else None
    if series.get("guide_id") and kept is None:  # the user picked the guide: no casting call
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
        result = await casting_director(deps.llm, brief, series["title"] or series["topic"], design, library, kept,
                                        genre=series["genre"] or "")
    except Exception as exc:  # the cast is a quality step: without it the Art director invents the guide
        log.warning("casting failed for %s: %s", job["series_id"], exc)
        return kept or [], cost if kept else 0.0
    by_id = {c["id"]: c for c in library}
    mascot = bool(design and design.brand and design.brand.mascot)
    private = mascot or brief.brand_characters  # a brand's mascot or a licensed character is never lent out
    style = (design.art_style if design and design.art_style else SHEET_STYLE)
    said = _words(" ".join(filter(None, [series["topic"], series["extra_instructions"]])))  # what the user wrote
    cast, cost = (list(kept), cost) if kept else ([], 0.0)
    members = list(result.value.cast)
    if kept:  # someone already in the cast is never cast again, whatever the director answered
        names = {normalize_subject(c["name"]) for c in kept}
        members = [m for m in members if normalize_subject(m.name) not in names]
    book, told = await _previous_book(deps, series) if kept and paint and deps.images is not None else ([], set())

    def drawn_before(name: str) -> bool:
        """A character the previous tome of the series already drew: its pages are its reference."""
        return bool(book) and bool(_words(name)) and _words(name) <= told

    async def paint_new(m):
        """A new character's sheet (from the previous tome's pages when they drew it, else from its parent's when
        it is based on one); None when painting failed."""
        if drawn_before(m.name):
            try:
                return await paint_sheet(deps.images, getattr(deps, "vision", None),
                                         FROM_BOOK.format(name=m.name) + sheet_prompt(m, style, False), book, m.name)
            except Exception as exc:
                log.warning("model sheet failed for %s: %s", m.name, exc)
                return None
        parent = by_id.get(m.based_on) if m.based_on else None
        refs = []
        if parent:
            try:
                refs = [reference_image(await deps.storage.download(parent["sheet_key"], bucket="images"))]
            except Exception:
                log.warning("sheet %s unavailable", parent["sheet_key"])
        try:
            return await paint_sheet(deps.images, getattr(deps, "vision", None), sheet_prompt(m, style, bool(refs)),
                                     refs, m.name)
        except Exception as exc:
            log.warning("model sheet failed for %s: %s", m.name, exc)
            return None

    # The new characters' sheets are painted at once: one after another they kept the cover waiting minutes.
    new = [m for m in members if not m.reuse or drawn_before(m.name)] if paint and deps.images is not None else []
    painted = dict(zip(map(id, new), await asyncio.gather(*map(paint_new, new))))
    for c in cast:  # kept without a sheet (the previous tome drew them from its text): painted from its pages too
        if not c.get("sheet_key") and drawn_before(c["name"]):
            try:
                image, spent = await paint_sheet(deps.images, getattr(deps, "vision", None),
                                                 FROM_BOOK.format(name=c["name"]) + sheet_prompt(c, style, False),
                                                 book, c["name"])
            except Exception as exc:
                log.warning("model sheet failed for %s: %s", c["name"], exc)
                continue
            slug = normalize_subject(c["name"]).replace(" ", "-")
            c["sheet_key"], cost = f"characters/{job['series_id']}-{slug}.jpg", cost + spent
            await deps.storage.upload(c["sheet_key"], await asyncio.to_thread(_jpeg, image.data), "image/jpeg",
                                      bucket="images")
    for m in members:
        if m.reuse and not drawn_before(m.name):
            row = by_id[m.reuse]
            if row["name"] == row["archetype"] and m.name != row["name"]:  # a library character without its name
                row = {**row, "name": m.name}
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
        if painted[id(m)] is None:
            cast.append(_entry(None, m.model_dump(), None))
            continue
        image, spent = painted[id(m)]
        parent = by_id.get(m.based_on) if m.based_on and not drawn_before(m.name) else None
        cost += spent
        char_id = str(uuid.uuid4())
        key = f"characters/{char_id}.jpg"
        # A name the user wrote (a child of their class, a relative) stays in their tome; the library shows the
        # character by what it is, and whoever borrows it names it again.
        personal = bool(_words(m.name) & said)
        shelf_name = m.archetype[:1].upper() + m.archetype[1:] if personal else m.name
        topics = [t for t in [" ".join(w for w in topic.split() if w not in _words(m.name))] if t] if personal else [topic]
        await deps.storage.upload(key, await asyncio.to_thread(_jpeg, image.data), "image/jpeg", bucket="images")
        async with deps.engine.begin() as conn:
            await conn.execute(text(
                """insert into public.characters (id, name, role, archetype, look, personality, signature, palette,
                          style, topics, audience, sheet_key, based_on, user_id, shared, use_count)
                   values (:id, :name, :role, :arch, :look, :pers, :sig, :pal, :style, :t, :aud, :key,
                           :parent, :u, :shared, 1)"""),
                {"id": char_id, "name": shelf_name, "role": m.role if m.role in ("guide", "companion") else "guide",
                 "arch": m.archetype, "look": m.look, "pers": m.personality, "sig": m.signature, "pal": m.palette,
                 "style": style, "t": topics, "aud": brief.audience, "key": key,
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


FROM_BOOK = ("The attached images are pages of the previous book of this series: draw {name} exactly as there (face, "
             "skin, hair, outfit, colours, proportions); if {name} is not in them, ignore them. ")


async def _previous_book(deps, series) -> tuple[list[bytes], set[str]]:
    """The tome this one continues: its first painted pages and the words its pages say, to recognise the
    characters it already drew. Nothing when the tome continues none."""
    if not series.get("source_id"):
        return [], set()
    from app.jobs import _plate_images  # jobs imports this module

    async with deps.engine.connect() as conn:
        pages = (await conn.execute(text("select content_json::text from public.lessons where series_id = :s"),
                                    {"s": series["source_id"]})).scalars().all()
    told = _words(" ".join(p for p in pages if p))
    return (await _plate_images(deps, series["source_id"], 3) if told else []), told


SHEET_CHECK = ("Hoja de modelo de un solo personaje, {name}: vistas de cuerpo entero y cuatro cabezas con "
               "expresiones. Cada figura tiene una sola cabeza con una sola cara (de perfil, un solo perfil); es un "
               "defecto una cabeza con dos caras, ojos, hocicos, patas, brazos o colas de más.")


async def paint_sheet(images, vision, prompt: str, references: list[bytes], name: str):
    """A model sheet, checked by the image Reviewer: a sheet is the reference for every page, so a two-faced head
    on it repeats through the book. One repaint with the defect named; returns the image and what it all cost."""
    image = await images.generate(prompt, references=references, aspect_ratio="4:3", resolution="2K")
    cost = image.cost_usd or 0.0
    if vision is None:
        return image, cost
    try:
        verdict = (await vision.review_sheet(image.data, [SHEET_CHECK.format(name=name)], kind="illustration"))[0]
    except Exception as exc:  # the review is a safeguard, not a gate
        log.warning("sheet review of %s failed: %s", name, exc)
        return image, cost
    cost += verdict.cost_usd or 0.0
    if verdict.ok:
        return image, cost
    log.info("sheet of %s repainted: %s", name, verdict.issues)
    retry = await images.generate(f"{prompt} Fix these problems from the previous attempt: "
                                  f"{verdict.issues or 'a deformed head'}.", references=references,
                                  aspect_ratio="4:3", resolution="2K")
    return retry, cost + (retry.cost_usd or 0.0)


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
        image, spent = await paint_sheet(deps.images, getattr(deps, "vision", None),
                                         RESTYLE + sheet_prompt(row, design.art_style or SHEET_STYLE, False), [base],
                                         row["name"])
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
    return key, spent


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
    image, _ = await paint_sheet(deps.images, getattr(deps, "vision", None), sheet_prompt(m, style, bool(refs)), refs,
                                 m.name)
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


def _words(text_: str | None) -> set[str]:
    """Proper-name-sized words, accent- and case-blind, to tell a name the user wrote."""
    return {w for w in normalize_subject(text_ or "").split() if len(w) > 2}


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
              "short wagging tail, a blue neckerchief. Round body, short legs, big head; one head with one face, "
              "drawn simply."),
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


async def keep_seeded(engine, images, storage, vision=None) -> None:
    """The worker's background task: the starter characters and their sheets, painted once (8 × ~$0.07). A starter
    whose description changed (a sheet that came out wrong) is painted again, and its sheets in the house styles,
    drawn from the old one, are dropped so each is redrawn the next time a tome asks for it."""
    for c in SEED:
        async with engine.begin() as conn:
            row = (await conn.execute(text("select id, sheet_key, look from public.characters where seed and name = :n"),
                                      {"n": c["name"]})).one_or_none()
        if row and row.sheet_key and row.look == c["look"]:
            continue
        try:
            image, _ = await paint_sheet(images, vision, sheet_prompt(c, SHEET_STYLE, False), [], c["name"])
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
                   on conflict (id) do update set sheet_key = excluded.sheet_key, look = excluded.look,
                                                  signature = excluded.signature"""),
                {"id": char_id, **c, "style": SHEET_STYLE, "key": key})
            await conn.execute(text("delete from public.character_sheets where character_id = :id"), {"id": char_id})
        log.info("seeded character %s", c["name"])
        await asyncio.sleep(PAUSE_SECONDS)


FROM_COVER = ("The attached image is this book's cover: if {name} is on it, draw exactly that character (face, skin, "
              "hair, outfit, colours, proportions); if not, ignore it. ")


async def complete_sheets(deps, series_id, design: Design | None) -> tuple[list[dict], float]:
    """A tome begun as a free preview cast its characters without model sheets (a preview paints none). Once it is
    paid, the cover and the plates paint them first, from the cover the user already saw, so the new cover and every
    plate draw the same faces. The cover job and the sections start together: the first one paints, the rest wait for
    it. Returns the cast and what painting cost."""
    from app.jobs import _json  # jobs imports this module

    async with deps.engine.begin() as conn:
        await conn.execute(text("select pg_advisory_xact_lock(hashtext(:k))"), {"k": f"sheets:{series_id}"})
        row = (await conn.execute(text('select "cast", cover_key from public.series where id = :s'),
                                  {"s": series_id})).mappings().one()
        cast = _json(row["cast"]) or []
        if deps.images is None or all(c.get("sheet_key") for c in cast):
            return cast, 0.0
        refs = []
        if row["cover_key"]:
            try:
                refs = [reference_image(await deps.storage.download(row["cover_key"]))]
            except Exception:
                log.warning("cover %s unavailable for the sheets", row["cover_key"])
        style = design.art_style if design and design.art_style else SHEET_STYLE
        async def paint(c):
            prompt = (FROM_COVER.format(name=c["name"]) if refs else "") + sheet_prompt(c, style, False)
            try:
                return await paint_sheet(deps.images, getattr(deps, "vision", None), prompt, refs, c["name"])
            except Exception as exc:  # without a sheet the character is drawn from its description, as before
                log.warning("model sheet failed for %s: %s", c["name"], exc)
                return None

        missing = [i for i, c in enumerate(cast) if not c.get("sheet_key")]
        painted = await asyncio.gather(*(paint(cast[i]) for i in missing))  # at once: the cover waits for them
        cost = 0.0
        for i, done in zip(missing, painted):
            if done is None:
                continue
            c, (image, spent) = cast[i], done
            key = f"characters/{series_id}-{i}.jpg"
            await deps.storage.upload(key, await asyncio.to_thread(_jpeg, image.data), "image/jpeg", bucket="images")
            c["sheet_key"], cost = key, cost + spent
        await conn.execute(text('update public.series set "cast" = cast(:c as jsonb) where id = :s'),
                           {"s": series_id, "c": json.dumps(cast)})
    return cast, cost
