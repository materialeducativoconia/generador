"""The Layout agent (code, no AI): content_json → HTML → PDF with WeasyPrint.

Exact drawings (piano keys, tracing letters, letter grids) are generated here as SVG/HTML,
because image models get them wrong and code doesn't.
"""

import base64
import html
import random
import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from app.themes import DEFAULT_PALETTE, ORNAMENTS, THEMES, mix
from app.content import Design, Keyboard, LetterGrid, SectionContent, Tracing

ASSETS = Path(__file__).parent / "assets"
TEMPLATES = Path(__file__).parent / "templates"

WHITE_NOTES = ["C", "D", "E", "F", "G", "A", "B"]
NOTE_NAMES_ES = {"C": "Do", "D": "Re", "E": "Mi", "F": "Fa", "G": "Sol", "A": "La", "B": "Si"}
GENRE_LABEL = {"coloring_book": "Libro para colorear", "worksheets": "Cuadernillo de actividades",
               "tutorial": "Método paso a paso", "lesson_series": "Secuencia didáctica"}


@dataclass
class TomeSection:
    position: int
    title: str
    content: SectionContent


@dataclass
class Tome:
    title: str
    genre: str
    audience: str
    author: str | None
    sections: list[TomeSection]
    cover_image: bytes | None = None
    cover_media_type: str = "image/png"
    palette: list[str] | None = None  # [background, ink, accent] from the cover agent
    design: Design | None = None  # the Designer's theme; None means the classic theme

    @property
    def cover_data_uri(self) -> str | None:
        if not self.cover_image:
            return None
        return f"data:{self.cover_media_type};base64,{base64.b64encode(self.cover_image).decode()}"


def inline(value: str) -> Markup:
    """**bold** and *italic* only, applied after escaping, so model output can never inject HTML."""
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", escaped)
    return Markup(escaped)


def keyboard_svg(block: Keyboard, lit_white: str = "#c7d2fe", lit_black: str = "#4f46e5") -> Markup:
    octave = int(block.start[-1])
    start_index = WHITE_NOTES.index(block.start[0])
    whites = []
    for i in range(7 * block.octaves):
        idx = start_index + i
        whites.append(f"{WHITE_NOTES[idx % 7]}{octave + idx // 7}")
    lit = set(block.highlight)
    w, h, bw, bh = 34, 150, 20, 92
    parts = []
    for i, note in enumerate(whites):
        cls, fill = ("white on", lit_white) if note in lit else ("white", "#ffffff")
        parts.append(f'<rect class="{cls}" x="{i * w}" y="0" width="{w}" height="{h}" rx="3" fill="{fill}" '
                     f'stroke="#1c1917" stroke-width="1.4"/>')
        if block.show_labels:
            label = NOTE_NAMES_ES[note[0]]
            parts.append(f'<text class="label" x="{i * w + w / 2}" y="{h - 12}" text-anchor="middle" '
                         f'font-family="Nunito" font-weight="700" font-size="10" fill="#57534e">{label}</text>')
    for i, note in enumerate(whites[:-1]):
        if note[0] in "CDFGA":
            sharp = f"{note[0]}#{note[1:]}"
            cls, fill = ("black on", lit_black) if sharp in lit else ("black", "#1c1917")
            parts.append(f'<rect class="{cls}" x="{(i + 1) * w - bw / 2}" y="0" width="{bw}" height="{bh}" rx="2" '
                         f'fill="{fill}"/>')
    width = len(whites) * w
    return Markup(f'<svg class="keyboard" viewBox="-1 -1 {width + 2} {h + 2}" width="{min(width, 640)}" '
                  f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>')


def tracing_svg(block: Tracing) -> Markup:
    text = html.escape(block.text)
    rows = []
    for r in range(block.repeat):
        y = r * 70
        paint = 'fill="#1c1917"' if r == 0 else 'fill="none" stroke="#8a8580" stroke-width="1.3" stroke-dasharray="3 3.5"'
        rows.append(
            f'<line x1="0" x2="600" y1="{y + 10}" y2="{y + 10}" stroke="#a8a29e" stroke-width="1"/>'
            f'<line x1="0" x2="600" y1="{y + 32}" y2="{y + 32}" stroke="#a8a29e" stroke-width="1" stroke-dasharray="4 4"/>'
            f'<line x1="0" x2="600" y1="{y + 54}" y2="{y + 54}" stroke="#57534e" stroke-width="1.4"/>'
            f'<text x="6" y="{y + 54}" font-family="Andika" font-size="58" letter-spacing="18" {paint}>{text}</text>'
        )
    height = block.repeat * 70
    return Markup(f'<svg class="tracing" viewBox="0 0 600 {height}" width="600" height="{height}" '
                  f'xmlns="http://www.w3.org/2000/svg">{"".join(rows)}</svg>')


def letter_grid_cells(block: LetterGrid) -> list[tuple[str, bool]]:
    rng = random.Random(f"{block.id}:{block.targets}:{block.distractors}")  # same tome → same grid
    total = block.rows * block.cols
    n_targets = max(len(block.targets), round(total * 0.35))
    cells = [block.targets[i % len(block.targets)] for i in range(n_targets)]
    cells += [rng.choice(block.distractors) for _ in range(total - n_targets)]
    rng.shuffle(cells)
    return [(c, c in block.targets) for c in cells]


_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["j2"]),
                   trim_blocks=True, lstrip_blocks=True)
_env.filters["inline"] = inline
_env.globals.update(keyboard_svg=keyboard_svg, tracing_svg=tracing_svg, letter_grid_cells=letter_grid_cells,
                    GENRE_LABEL=GENRE_LABEL)


def render_html(tome: Tome, *, paper: str, include_answer_key: bool) -> str:
    answers = [
        (section, block)
        for section in tome.sections
        for block in section.content.blocks
        if block.type == "exercise" and block.answer
    ]
    th = THEMES[tome.design.theme if tome.design else "clasico"]
    bg, ink, accent = (tome.design.palette if tome.design else None) or tome.palette or DEFAULT_PALETTE
    colors = {"ink": ink, "accent": accent, "tint": mix(bg, accent, 0.28), "soft": mix("#FFFFFF", accent, 0.09),
              "line": mix("#FFFFFF", ink, 0.18), "muted": mix(ink, "#FFFFFF", 0.38)}
    theme_fonts = sorted({(th.head, th.head_file), (th.body, th.body_file)} - {("Andika", "Andika-Regular.ttf"),
                                                                              ("Nunito", "Nunito-Variable.ttf")})
    return _env.get_template("tome.html.j2").render(
        tome=tome, paper=paper, answers=answers if include_answer_key else [], fonts=(ASSETS / "fonts").as_uri(),
        th=th, c=colors, head=f'"{th.head}"', body=f'"{th.body}"', theme_fonts=theme_fonts,
        ornament=ORNAMENTS[tome.design.ornament] if tome.design else "",
    )


def _asset_fetcher():
    """Only our bundled assets may load: no network, so no SSRF through content."""
    from weasyprint.urls import URLFetcher

    class AssetFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            if not (url.startswith(ASSETS.as_uri() + "/") or url.startswith("data:image/")):
                raise ValueError(f"blocked resource: {url}")
            return super().fetch(url, headers)

    return AssetFetcher(allowed_protocols=["file", "data"])


def render_pdf(tome: Tome, *, paper: str, include_answer_key: bool) -> tuple[bytes, int]:
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    # Without a FontConfiguration, WeasyPrint silently ignores @font-face.
    document = HTML(string=render_html(tome, paper=paper, include_answer_key=include_answer_key),
                    base_url=ASSETS.as_uri(), url_fetcher=_asset_fetcher()).render(font_config=FontConfiguration())
    return document.write_pdf(), len(document.pages)
