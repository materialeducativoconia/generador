"""The Layout agent (code, no AI): content_json → HTML → PDF with WeasyPrint.

Exact drawings (piano keys, tracing letters, letter grids) are generated here as SVG/HTML,
because image models get them wrong and code doesn't.
"""

import base64
import html
import random
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from app.printing import BLEED_MM, PAPERS, SPINE_TEXT_PAGES, is_color, page_geometry, spine_mm
from app.themes import DEFAULT_PALETTE, FRAMES, ORNAMENTS, THEMES, mix, theme_for
from app.content import DIAGRAM_TYPES, WORKSHEET_TYPES, Design, Keyboard, LetterGrid, SectionContent, Tracing
from app.diagrams import render_diagram
from app.worksheets import answers as worksheet_answers, render_worksheet

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
    images: dict[str, tuple[bytes, str]] = field(default_factory=dict)  # asset id -> (bytes, media type)
    credits: dict[str, str] = field(default_factory=dict)  # asset id -> attribution, for photos we did not make
    sources: list[dict] = field(default_factory=list)  # the Researcher's documents: {title, url}

    def image_uri(self, asset_id: str | None) -> str | None:
        if not asset_id or asset_id not in self.images:
            return None
        data, media_type = self.images[asset_id]
        return f"data:{media_type};base64,{base64.b64encode(data).decode()}"

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
                    GENRE_LABEL=GENRE_LABEL, render_diagram=render_diagram, DIAGRAM_TYPES=DIAGRAM_TYPES,
                    render_worksheet=render_worksheet, WORKSHEET_TYPES=WORKSHEET_TYPES)


def theme_colors(design: Design | None, palette: list[str] | None = None):
    """The theme and its colours: the web preview's diagrams use these too."""
    th = theme_for(design)
    bg, ink, accent = (design.palette if design else None) or palette or DEFAULT_PALETTE
    return th, {"ink": ink, "accent": accent, "tint": mix(bg, accent, 0.28), "soft": mix("#FFFFFF", accent, 0.09),
                "line": mix("#FFFFFF", ink, 0.18), "muted": mix(ink, "#FFFFFF", 0.38)}


def _look(tome: Tome) -> dict:
    """Theme, colours and fonts shared by the interior and the cover wrap."""
    th, colors = theme_colors(tome.design, tome.palette)
    theme_fonts = sorted({(th.head, th.head_file), (th.body, th.body_file)} - {("Andika", "Andika-Regular.ttf"),
                                                                              ("Nunito", "Nunito-Variable.ttf")})
    border, radius = FRAMES[tome.design.frame if tome.design else "none"]
    return {"th": th, "c": colors, "head": f'"{th.head}"', "body": f'"{th.body}"', "theme_fonts": theme_fonts,
            "fonts": (ASSETS / "fonts").as_uri(), "frame": {"border": border, "radius": radius,
                                                         "pad": 0 if border == "none" else 4}}


def render_html(tome: Tome, *, paper: str, include_answer_key: bool, print_edition: bool = False,
                fit: dict[str, float] | None = None) -> str:
    """The interior. The print edition swaps the cover for a title page (the cover is its own file) and
    mirrors the margins so the binding side is wider."""
    answers = []
    for section in tome.sections:
        for block in section.content.blocks:
            if block.type == "exercise" and block.answer:
                answers.append((section, block))
            for prompt, answer in worksheet_answers(block):  # counting and picture maths: computed, not written
                answers.append((section, SimpleNamespace(prompt=prompt, answer=answer, explanation=None)))
    return _env.get_template("tome.html.j2").render(
        tome=tome, paper=paper, answers=answers if include_answer_key else [], print_edition=print_edition,
        fit=fit or {},
        geo=page_geometry(paper, print_edition=print_edition),
        ornament=ORNAMENTS[tome.design.ornament] if tome.design else "", **_look(tome),
    )


def render_cover_wrap(tome: Tome, *, paper: str, pages: int) -> tuple[bytes, str]:
    """One sheet for the printer: back cover, spine and front, with bleed on every edge."""
    w, h = PAPERS[paper]
    spine = spine_mm(pages, color=is_color(tome))
    wrap = {"bleed": BLEED_MM, "w": w, "h": h, "spine": spine, "total_w": round(2 * w + spine + 2 * BLEED_MM, 3),
            "total_h": round(h + 2 * BLEED_MM, 3), "spine_text": pages >= SPINE_TEXT_PAGES}
    html = _env.get_template("cover_wrap.html.j2").render(tome=tome, wrap=wrap, **_look(tome))
    return _write_pdf(html)[0], html


def _asset_fetcher():
    """Only our bundled assets may load: no network, so no SSRF through content."""
    from weasyprint.urls import URLFetcher

    class AssetFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            if not (url.startswith(ASSETS.as_uri() + "/") or url.startswith("data:image/")):
                raise ValueError(f"blocked resource: {url}")
            return super().fetch(url, headers)

    return AssetFetcher(allowed_protocols=["file", "data"])


def _document(html: str):
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    # Without a FontConfiguration, WeasyPrint silently ignores @font-face.
    return HTML(string=html, base_url=ASSETS.as_uri(), url_fetcher=_asset_fetcher()).render(
        font_config=FontConfiguration())


def _write_pdf(html: str) -> tuple[bytes, int]:
    document = _document(html)
    return document.write_pdf(), len(document.pages)


PX_MM = 25.4 / 96
FIT_MIN = 0.55  # a fitted picture keeps at least this share of its normal height, or it is not worth it


def _pages(document) -> list[dict]:
    """Per page: how full the content area is, and the first block that starts it."""
    out = []
    for page in document.pages:
        box = page._page_box
        top, height = box.content_box_y(), box.height
        flow = [b for child in box.children if type(child).__name__ != "MarginBox" for b in child.descendants()]
        # Leaves only: containers (the section, the body) stretch to the page bottom when they continue.
        bottoms = [b.position_y + b.margin_height() for b in flow if hasattr(b, "margin_height") and (
            type(b).__name__ == "LineBox" or "Replaced" in type(b).__name__ or not getattr(b, "children", None))]
        first = next((b for b in flow if getattr(b, "element", None) is not None and b.element.get("data-block")), None)
        out.append({"fill": (max(bottoms, default=top) - top) / height, "free_px": height - (max(bottoms, default=top) - top),
                    "first": first.element.get("data-block") if first is not None and abs(first.position_y - top) < 2 else None,
                    "first_free": first is not None and first.element.get("data-free") == "1",
                    "lines": sum(1 for b in flow if type(b).__name__ == "LineBox")})
    return out


def render_checked(tome: Tome, *, paper: str, include_answer_key: bool,
                   print_edition: bool = False) -> tuple[bytes, int, dict]:
    """Render, then repair what a layout editor would: a picture that did not fit is shrunk into the gap it
    left behind (the page before it is half empty). Reports nearly empty pages it cannot fix."""
    geo = page_geometry(paper, print_edition=print_edition)
    sizes = {f"{s.position}:{b.id}": (b.size, b.subject) for s in tome.sections for b in s.content.blocks
             if b.type == "image"}
    fit: dict[str, float] = {}
    for _ in range(3):  # each pass can only move pictures back; two repairs are plenty
        document = _document(render_html(tome, paper=paper, include_answer_key=include_answer_key,
                                         print_edition=print_edition, fit=fit))
        pages = _pages(document)
        new = {}
        for before, page in zip(pages, pages[1:]):
            key = page["first"]
            if key not in sizes or key in fit or page["first_free"] or before["fill"] > 0.8:
                continue
            normal = getattr(geo, sizes[key][0])
            height = round(before["free_px"] * PX_MM - 14, 1)  # figure margins and a caption
            if height >= normal * FIT_MIN:
                new[key] = min(height, normal)
        if not new:
            break
        fit.update(new)
    issues = [f"Página {i + 1} casi vacía ({p['lines']} líneas)" for i, p in enumerate(pages)
              if i > 0 and p["fill"] < 0.12 and not p["first"]]
    return document.write_pdf(), len(document.pages), {"fixed": [sizes[k][1] for k in fit], "issues": issues}


def render_pdf(tome: Tome, *, paper: str, include_answer_key: bool, print_edition: bool = False) -> tuple[bytes, int]:
    """The plain render; exports use render_checked."""
    return _write_pdf(render_html(tome, paper=paper, include_answer_key=include_answer_key,
                                  print_edition=print_edition))
