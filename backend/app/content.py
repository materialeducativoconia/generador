"""The page-block catalog: the only shape the LLM may produce, the editor shows and the PDF renders.

Inline formatting is limited to **bold** and *italic*; it is parsed after HTML-escaping, never trusted as HTML.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Genre = Literal["coloring_book", "worksheets", "tutorial", "lesson_series"]
Note = Annotated[str, Field(pattern=r"^[A-G]#?[1-7]$")]  # scientific pitch, e.g. C4, F#3
Text = Annotated[str, Field(min_length=1, max_length=4000)]
Short = Annotated[str, Field(min_length=1, max_length=300)]


class _Block(BaseModel):
    id: Annotated[str, Field(min_length=1, max_length=20)]


class Heading(_Block):
    type: Literal["heading"]
    level: Literal[2, 3] = 2
    text: Short


class Paragraph(_Block):
    type: Literal["paragraph"]
    text: Text


class ListBlock(_Block):
    type: Literal["list"]
    style: Literal["bullet", "number", "check"] = "bullet"
    items: list[Short] = Field(min_length=1, max_length=30)


class Callout(_Block):
    type: Literal["callout"]
    variant: Literal["key_idea", "tip", "warning", "fun_fact"] = "key_idea"
    title: Short | None = None
    text: Text


class Table(_Block):
    type: Literal["table"]
    caption: Short | None = None
    headers: list[Short] = Field(min_length=1, max_length=8)
    rows: list[list[str]] = Field(min_length=1, max_length=40)


class Example(_Block):
    type: Literal["example"]
    title: Short | None = None
    text: Text


class Activity(_Block):
    type: Literal["activity"]
    title: Short
    duration_minutes: int | None = Field(default=None, ge=1, le=240)
    materials: list[Short] = Field(default_factory=list, max_length=20)
    steps: list[Text] = Field(min_length=1, max_length=20)


class Exercise(_Block):
    type: Literal["exercise"]
    kind: Literal["open", "multiple_choice", "true_false", "fill_blank"]
    prompt: Text
    options: list[Short] = Field(default_factory=list, max_length=8)
    answer: str | None = None  # goes to the answer key, never to the student's page
    explanation: str | None = None
    answer_space_lines: int = Field(default=0, ge=0, le=20)


class Keyboard(_Block):
    """Piano keyboard drawn exactly by code (image models get the key pattern wrong)."""

    type: Literal["keyboard"]
    start: Note = "C4"
    octaves: int = Field(default=1, ge=1, le=3)
    highlight: list[Note] = Field(default_factory=list, max_length=24)
    show_labels: bool = True
    caption: Short | None = None


class Tracing(_Block):
    """Dotted text to trace over, on handwriting guide lines."""

    type: Literal["tracing"]
    text: Annotated[str, Field(min_length=1, max_length=80)]
    repeat: int = Field(default=3, ge=1, le=12)
    instruction: Short | None = None


class LetterGrid(_Block):
    """Grid of circled letters/syllables: the child colours the targets."""

    type: Literal["letter_grid"]
    targets: list[Annotated[str, Field(min_length=1, max_length=4)]] = Field(min_length=1, max_length=6)
    distractors: list[Annotated[str, Field(min_length=1, max_length=4)]] = Field(min_length=1, max_length=20)
    rows: int = Field(default=6, ge=2, le=10)
    cols: int = Field(default=6, ge=2, le=8)
    instruction: Short | None = None


class Image(_Block):
    """An image request; phase 1 renders a placeholder, later the Illustrator/Curator fills `asset_id`."""

    type: Literal["image"]
    kind: Literal["line_art", "illustration", "photo", "diagram"]
    subject: Short  # what to draw, e.g. "una ardilla con una bellota"
    caption: Short | None = None
    size: Literal["full", "half", "small"] = "half"
    asset_id: str | None = None


# Diagrams drawn exactly by code (app.diagrams): free, instant, real text, never a garbled picture.
Label = Annotated[str, Field(min_length=1, max_length=80)]


class StaffNote(BaseModel):
    pitch: Note | Literal["rest"]
    duration: Literal["whole", "half", "quarter", "eighth"] = "quarter"


class Staff(_Block):
    """Musical staff: clef, optional time signature, notes or rests, optional note names."""

    type: Literal["staff"]
    clef: Literal["treble", "bass"] = "treble"
    time: Literal["2/4", "3/4", "4/4"] | None = None
    notes: list[StaffNote] = Field(min_length=1, max_length=16)
    show_names: bool = False
    caption: Short | None = None


class TimelineEvent(BaseModel):
    when: Annotated[str, Field(min_length=1, max_length=40)]
    label: Label


class Timeline(_Block):
    type: Literal["timeline"]
    events: list[TimelineEvent] = Field(min_length=2, max_length=10)
    caption: Short | None = None


class Cycle(_Block):
    """Steps joined by arrows: a closed cycle (water, life cycle) or an open process."""

    type: Literal["cycle"]
    steps: list[Label] = Field(min_length=3, max_length=8)
    closed: bool = True
    caption: Short | None = None


class BarChart(_Block):
    type: Literal["bar_chart"]
    labels: list[Annotated[str, Field(min_length=1, max_length=30)]] = Field(min_length=2, max_length=10)
    values: list[Annotated[float, Field(ge=0)]] = Field(min_length=2, max_length=10)
    unit: Annotated[str, Field(max_length=30)] | None = None
    caption: Short | None = None

    @model_validator(mode="after")
    def _same_length(self):
        if len(self.labels) != len(self.values):
            raise ValueError("labels y values deben tener la misma cantidad de elementos.")
        return self


class NumberLine(_Block):
    """Ticks from start to end; `marks` are highlighted, `blanks` become empty boxes for the student."""

    type: Literal["number_line"]
    start: int = Field(ge=-1000, le=1000)
    end: int = Field(ge=-1000, le=1000)
    step: int = Field(default=1, ge=1, le=1000)
    marks: list[int] = Field(default_factory=list, max_length=10)
    blanks: list[int] = Field(default_factory=list, max_length=10)
    caption: Short | None = None

    @model_validator(mode="after")
    def _range(self):
        if self.end <= self.start or (self.end - self.start) // self.step > 30:
            raise ValueError("La recta va de start a end (end > start) con 30 marcas como máximo.")
        return self


class FractionPart(BaseModel):
    numerator: int = Field(ge=0, le=12)
    denominator: int = Field(ge=1, le=12)

    @model_validator(mode="after")
    def _proper(self):
        if self.numerator > self.denominator:
            raise ValueError("El numerador no puede superar al denominador.")
        return self


class Fraction(_Block):
    type: Literal["fraction"]
    fractions: list[FractionPart] = Field(min_length=1, max_length=4)
    shape: Literal["circle", "bar"] = "circle"
    shaded: bool = True  # False: every part blank, for the student to colour
    show_label: bool = True
    caption: Short | None = None


class Clock(_Block):
    type: Literal["clock"]
    times: list[Annotated[str, Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")]] = Field(min_length=1, max_length=4)
    show_hands: bool = True  # False: an empty face for the student to draw the hands
    show_time: bool = False  # the written time under each clock
    caption: Short | None = None


DIAGRAM_TYPES = ("staff", "timeline", "cycle", "bar_chart", "number_line", "fraction", "clock")


# Literacy worksheets drawn by code (app.worksheets). The Writer picks letters, words and sentences; the code
# lays out the page. `pictures` maps a word to its drawing in the shared icon library, filled by the Illustrator.
Word = Annotated[str, Field(min_length=1, max_length=24, pattern=r"^[^\s<>]+$")]
Syllable = Annotated[str, Field(min_length=1, max_length=5, pattern=r"^[^\s<>]+$")]
CardText = Annotated[str, Field(min_length=1, max_length=12, pattern=r"^[^\s<>]+$")]  # a syllable or a whole word


class _Pictured(_Block):
    instruction: Short | None = None
    pictures: dict[str, str] = Field(default_factory=dict)


class ChartWord(BaseModel):
    word: Word
    syllable: Syllable


class SyllableChart(_Pictured):
    """The letter's template: big letter, then one cell per word with its picture and syllable."""

    type: Literal["syllable_chart"]
    letter: Syllable
    words: list[ChartWord] = Field(min_length=4, max_length=15)


class PictureWord(BaseModel):
    word: Word
    syllable: Syllable | None = None


class PictureWords(_Pictured):
    """write: name each picture on guide lines; complete: fill the missing syllable; circle: circle the
    syllable the word starts with; match: join each picture with its syllable."""

    type: Literal["picture_words"]
    mode: Literal["write", "complete", "circle", "match"] = "write"
    items: list[PictureWord] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def _syllables(self):
        if self.mode != "write" and any(not i.syllable for i in self.items):
            raise ValueError(f"En modo {self.mode} cada item necesita su syllable.")
        return self


class SyllableCards(_Block):
    """Syllables in cells, dashed to cut out (or to colour) and build words with."""

    type: Literal["syllable_cards"]
    syllables: list[CardText] = Field(min_length=4, max_length=40)
    cut: bool = True
    instruction: Short | None = None


class ReadingLine(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=160)]
    picture: Word | None = None


class Reading(_Pictured):
    """Sentences to read aloud, each with a box the teacher ticks; optional rubric legend."""

    type: Literal["reading"]
    title: Short | None = None
    sentences: list[ReadingLine] = Field(min_length=1, max_length=8)
    rubric: bool = True


class Dictation(_Block):
    """Numbered lines for a dictation; the words go to the teacher's box (or the answer key)."""

    type: Literal["dictation"]
    words: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=12)
    lines: int = Field(default=10, ge=3, le=12)
    show_words: bool = True
    title: Short | None = None


class FillItem(BaseModel):
    text: Annotated[str, Field(min_length=4, max_length=160, pattern=r"___")]
    answer: Word


class FillSentences(_Pictured):
    """Sentences with a blank; the answer's picture is the hint."""

    type: Literal["fill_sentences"]
    items: list[FillItem] = Field(min_length=1, max_length=6)


class WordSearch(_Pictured):
    type: Literal["word_search"]
    words: list[Word] = Field(min_length=3, max_length=8)
    size: int = Field(default=8, ge=6, le=12)

    @model_validator(mode="after")
    def _fits(self):
        if any(len(w) > self.size for w in self.words):
            raise ValueError("Cada palabra debe caber en la sopa de letras (size).")
        return self


class Classify(_Block):
    """Columns headed by syllables; the child sorts the word bank into them."""

    type: Literal["classify"]
    columns: list[Syllable] = Field(min_length=2, max_length=4)
    words: list[Word] = Field(min_length=4, max_length=16)
    instruction: Short | None = None


class DrawFrames(_Block):
    type: Literal["draw_frames"]
    count: int = Field(default=3, ge=1, le=6)
    labels: list[Annotated[str, Field(max_length=40)]] = Field(default_factory=list, max_length=6)
    instruction: Short | None = None


def block_assets(block: dict) -> list[str]:
    """Asset ids a stored block points at: an image's picture, or a worksheet's word pictures."""
    ids = [block["asset_id"]] if block.get("type") == "image" and block.get("asset_id") else []
    return ids + list((block.get("pictures") or {}).values())


class CountItem(BaseModel):
    object: Word  # one word, drawn once in the picture library and repeated `count` times by code
    count: int = Field(ge=1, le=20)
    rows: int | None = Field(default=None, ge=1, le=10)  # a rectangular array: rows of count / rows each

    @model_validator(mode="after")
    def _array(self):
        if self.rows and self.count % self.rows:
            raise ValueError(f"{self.count} no se reparte en {self.rows} filas iguales: ajusta count o rows.")
        return self


class Counting(_Pictured):
    """Count the pictures and write the number: the code draws exactly `count` copies."""

    type: Literal["counting"]
    items: list[CountItem] = Field(min_length=1, max_length=6)


class Operation(BaseModel):
    object: Word
    a: int = Field(ge=0, le=30)
    op: Literal["+", "-", "×", "÷"]
    b: int = Field(ge=1, le=10)

    @model_validator(mode="after")
    def _drawable(self):
        if self.op == "+" and self.a + self.b > 20:
            raise ValueError("Una suma con dibujos llega como mucho a 20.")
        if self.op == "-" and self.b > self.a:
            raise ValueError("En una resta con dibujos a debe ser mayor o igual que b.")
        if self.op == "×" and (self.a > 10 or self.a * self.b > 30):
            raise ValueError("Una multiplicación con dibujos tiene como mucho 30 figuras (a ≤ 10).")
        if self.op == "÷" and (self.a % self.b or self.a > 30):
            raise ValueError("Una división con dibujos debe ser exacta y tener como mucho 30 figuras.")
        return self

    @property
    def result(self) -> int:  # computed here, never taken from the model
        return {"+": self.a + self.b, "-": self.a - self.b, "×": self.a * self.b, "÷": self.a // self.b}[self.op]


class PictureMath(_Pictured):
    """Operations shown with pictures: a + b, a − b (b crossed out), a groups of b, a shared into b groups."""

    type: Literal["picture_math"]
    operations: list[Operation] = Field(min_length=1, max_length=6)


WORKSHEET_TYPES = ("syllable_chart", "picture_words", "syllable_cards", "reading", "dictation", "fill_sentences",
                   "word_search", "classify", "draw_frames", "counting", "picture_math")


class WritingLines(_Block):
    type: Literal["writing_lines"]
    lines: int = Field(default=4, ge=1, le=20)
    label: Short | None = None


class PageBreak(_Block):
    type: Literal["page_break"]


Block = Annotated[
    Heading | Paragraph | ListBlock | Callout | Table | Example | Activity | Exercise
    | Keyboard | Tracing | LetterGrid | Image | WritingLines | PageBreak
    | Staff | Timeline | Cycle | BarChart | NumberLine | Fraction | Clock
    | SyllableChart | PictureWords | SyllableCards | Reading | Dictation | FillSentences | WordSearch | Classify
    | DrawFrames | Counting | PictureMath,
    Field(discriminator="type"),
]


class SectionContent(BaseModel):
    schema_version: Literal[1] = 1
    summary: Annotated[str, Field(max_length=1000)] = ""
    blocks: list[Block] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [b.id for b in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("Los id de bloque deben ser únicos.")
        return self


class OutlineSection(BaseModel):
    title: Short
    objectives: list[Short] = Field(default_factory=list, max_length=6)
    key_points: list[Short] = Field(default_factory=list, max_length=12)
    letters: list[Syllable] = Field(default_factory=list, max_length=6)  # literacy: letters this section teaches
    pages: int | None = Field(default=None, ge=1, le=60)  # printed pages this section should fill


class Outline(BaseModel):
    title: Short
    genre: Genre
    style_notes: Annotated[str, Field(max_length=1000)] = ""
    known_letters: list[Syllable] = Field(default_factory=list, max_length=30)  # literacy: known before the tome
    sections: list[OutlineSection] = Field(min_length=1, max_length=20)

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class CoverPlan(BaseModel):
    """Art direction from the cover agent; the image model paints, our template sets the type."""

    concept: str = Field(min_length=3, max_length=400)
    search_queries: list[str] = Field(min_length=1, max_length=3)
    illustration_prompt: str = Field(min_length=20, max_length=1500)
    palette: list[Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]] = Field(min_length=3, max_length=3)


Hex = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


Ornament = Literal["estrellas", "notas", "hojas", "puntos", "formas", "ninguno"]
Frame = Literal["none", "line", "rounded", "dashed", "double"]
ArtStyle = Literal["acuarela", "crayon", "recorte", "gouache", "vector", "riso", "tinta", "plastilina", "grabado",
                   "infografia"]
CoverLayout = Literal["plate", "band", "framed"]
HeadFont = Literal["Fredoka", "Patrick Hand", "Fraunces", "Baloo 2", "Lexend", "Nunito", "Pacifico", "Sniglet"]


Mark = Literal["circle", "shield", "leaf", "star", "badge", "book"]


class Mascot(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    look: str = Field(min_length=3, max_length=300)  # English, fixed appearance repeated in every picture


class Brand(BaseModel):
    """An identity's editorial line: the imprint every tome of a collection carries, beside its Design."""

    name: str = Field(min_length=2, max_length=40)  # the imprint, e.g. «Semillita Ediciones»
    tagline: str = Field(default="", max_length=90)
    personality: list[Annotated[str, Field(max_length=30)]] = Field(default_factory=list, max_length=4)
    voice: str = Field(default="", max_length=400)  # Spanish, how the Writer addresses the reader
    mascot: Mascot | None = None  # recurring character in the line's covers and pictures
    mark: Mark = "circle"  # shape of the seal drawn by app.identity.mark_svg
    initials: str = Field(default="", max_length=3)


class Design(BaseModel):
    """The Designer's choice: one curated theme (app.themes), a palette and an ornament. A style from the
    user's library (Phase 9) also sets the heading font, a page frame and the illustration style. An identity
    adds its brand: the same look, seal, voice and mascot on every tome of a collection."""

    theme: Literal["juego", "cuaderno", "editorial", "metodo", "ciencia", "clasico"]
    palette: list[Hex] = Field(min_length=3, max_length=3)  # light background, ink, accent
    ornament: Ornament = "ninguno"
    rationale: str = Field(default="", max_length=400)
    head_font: HeadFont | None = None
    frame: Frame = "none"
    art_style: str | None = Field(default=None, max_length=500)  # English, for the image model
    style_id: str | None = None  # the library style it came from
    illustration: ArtStyle | None = None  # the Designer's pick in app.themes.ART_STYLES
    cover_layout: CoverLayout = "plate"
    identity_id: str | None = None  # the identity it came from
    brand: Brand | None = None


class BrandDirection(Brand):
    visual_idea: str = Field(default="", max_length=300)  # what the line should look like, for the designer


class BrandDirections(BaseModel):
    """The Brand strategist's proposals: three clearly different editorial lines."""

    directions: list[BrandDirection] = Field(min_length=3, max_length=3)


class IdentityLooks(BaseModel):
    """The Identity designer's visual system for each direction, in the same order."""

    looks: list[Design] = Field(min_length=3, max_length=3)

class StyleSpec(BaseModel):
    """The Style analyst's reading of a user's reference pages: style only, never their artwork or text."""

    best_pages: list[int] = Field(default_factory=list, max_length=4)  # 1-based, on the contact sheet
    score: int = Field(default=5, ge=1, le=10)  # how professional the design looks
    palette: list[Hex] = Field(min_length=3, max_length=3)  # background, ink, accent
    heading_look: Literal["rounded", "handwritten", "serif", "geometric", "script", "bubbly"] = "rounded"
    frame: Frame = "none"
    ornament: Ornament = "ninguno"
    density: Literal["airy", "balanced", "dense"] = "balanced"
    color_use: Literal["bw", "accents", "full"] = "accents"
    illustration_style: str = Field(default="", max_length=400)
    traits: list[Annotated[str, Field(max_length=160)]] = Field(default_factory=list, max_length=8)
    suits: str = Field(default="", max_length=240)


class Character(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    look: str = Field(min_length=3, max_length=300)  # fixed appearance, repeated in every prompt


class ArtPlan(BaseModel):
    """The Art director's style bible for every picture in a tome: one style, recurring characters."""

    style: str = Field(min_length=10, max_length=800)
    characters: list[Character] = Field(default_factory=list, max_length=4)
    prompts: dict[str, str] = Field(default_factory=dict)  # image ref -> rewritten prompt (English)
    photo_queries: dict[str, str] = Field(default_factory=dict)  # photo ref -> short English Commons search


class ResearchPlan(BaseModel):
    """Whether a tome needs sources (facts, history, science) or not (colouring book, piano method)."""

    needed: bool
    queries: list[str] = Field(default_factory=list, max_length=3)
    reason: str = Field(default="", max_length=300)
    program_queries: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=3)


class Fact(BaseModel):
    text: str = Field(min_length=5, max_length=300)
    source: int = Field(ge=1)  # 1-based index into the documents the Researcher read


class FactSheet(BaseModel):
    facts: list[Fact] = Field(default_factory=list, max_length=40)


class Level(BaseModel):
    """A level below or above the tome's, for a series by levels: what the programs teach on this topic there."""

    relation: Literal["anterior", "siguiente"]
    audience: str = Field(min_length=2, max_length=60)  # e.g. "Preescolar (5–6 años)"
    grade: str = Field(default="", max_length=160)  # where the program puts it, e.g. "SEP 2022, Fase 3, 1.º"
    focus: str = Field(min_length=5, max_length=300)  # what this topic covers at that level
    request: str = Field(min_length=10, max_length=400)  # a ready-to-send request for that tome
    source: int | None = Field(default=None, ge=1)


class ProgramSheet(BaseModel):
    """The reference syllabus the Architect follows: what an official or proven program teaches, in order."""

    program: str = Field(default="", max_length=300)  # e.g. "SEP 2022, Fase 3 (1.º y 2.º de primaria), Lenguajes"
    method: str = Field(default="", max_length=800)  # the teaching approach or the method's steps
    points: list[Fact] = Field(default_factory=list, max_length=30)  # contents in teaching order, with source
    levels: list[Level] = Field(default_factory=list, max_length=6)  # suggested tomes below and above this one


class ProgramReview(BaseModel):
    """The Program reviewer's check of an outline against the reference syllabus."""

    score: int = Field(ge=1, le=5)  # 5 = covers the program faithfully, in a sensible order
    covered: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=15)
    missing: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=10)
    issues: list[Annotated[str, Field(max_length=300)]] = Field(default_factory=list, max_length=8)


class Fix(BaseModel):
    """One correction from the Editor: replace a text field (or one item of a list field) of a block."""

    block_id: Annotated[str, Field(min_length=1, max_length=20)]
    field: Literal["text", "title", "prompt", "answer", "explanation", "caption", "label", "instruction", "items",
                   "options", "steps"]
    index: int | None = Field(default=None, ge=0, le=40)  # for items / options / steps
    text: Annotated[str, Field(min_length=1, max_length=4000)]


class EditReview(BaseModel):
    score: int = Field(ge=1, le=5)  # 5 = ready to sell as is
    issues: list[Annotated[str, Field(max_length=300)]] = Field(default_factory=list, max_length=8)
    fixes: list[Fix] = Field(default_factory=list, max_length=25)
