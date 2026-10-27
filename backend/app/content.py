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
    text: Annotated[str, Field(min_length=1, max_length=40)]
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


class WritingLines(_Block):
    type: Literal["writing_lines"]
    lines: int = Field(default=4, ge=1, le=20)
    label: Short | None = None


class PageBreak(_Block):
    type: Literal["page_break"]


Block = Annotated[
    Heading | Paragraph | ListBlock | Callout | Table | Example | Activity | Exercise
    | Keyboard | Tracing | LetterGrid | Image | WritingLines | PageBreak,
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


class Outline(BaseModel):
    title: Short
    genre: Genre
    style_notes: Annotated[str, Field(max_length=1000)] = ""
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
