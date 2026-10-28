"""Literacy worksheets drawn by code (no AI): syllable charts, picture words, cut-out cards, reading, dictation,
fill-in sentences, word search, classify and drawing frames.

Like app.diagrams, each renderer returns one inline <svg>, so the PDF and the web preview are the same picture.
Pictures come from `picture(asset_id) -> href | None` (a data URI in the PDF, a public URL on the web); a word
without a drawing yet gets a dashed placeholder. Everything a child reads — letters, syllables, words — is set in
Andika, a typeface made for learning to read; the theme's heading font only dresses titles and numbers.
"""

import random
import textwrap
from collections.abc import Callable
from html import escape

from markupsafe import Markup

from app.diagrams import _svg, _text
from app.literacy import _fold

W = 640
KID = "Andika, Nunito, sans-serif"
Picture = Callable[[str], str | None]


def render_worksheet(block, c: dict, font: str, picture: Picture | None = None, page: float = 860) -> Markup:
    """`page` is the height the worksheet may fill, in the same units as its 640-wide drawing: a ficha fills
    its page the way a printed workbook does, instead of floating at the top of it."""
    draw = {"syllable_chart": syllable_chart, "picture_words": picture_words, "syllable_cards": syllable_cards,
            "reading": reading, "dictation": dictation, "fill_sentences": fill_sentences,
            "word_search": word_search, "classify": classify, "draw_frames": draw_frames}[block.type]
    pics = getattr(block, "pictures", {}) or {}
    look = picture or (lambda _id: None)

    def pic(word: str, x: float, y: float, w: float, h: float) -> str:
        href = look(pics[word]) if word in pics else None
        if href:
            return (f'<image href="{escape(href)}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                    f'preserveAspectRatio="xMidYMid meet"/>')
        return (f'<rect class="pic-empty" x="{x + 3:.1f}" y="{y + 3:.1f}" width="{w - 6:.1f}" height="{h - 6:.1f}" '
                f'rx="8" fill="{c["soft"]}" stroke="{c["line"]}" stroke-dasharray="5 4"/>'
                + _text(x + w / 2, y + h / 2 + 5, word, KID, size=min(14, w / 6), fill=c["muted"], weight=400))

    head, top = _instruction(block, c, font)
    w, h, body = draw(block, c, font, pic, top, page - top)
    return Markup(_svg(f"ws {block.type.replace('_', '-')}", w, h, head + body))


def _instruction(block, c, font) -> tuple[list[str], float]:
    text = getattr(block, "instruction", None)
    if not text:
        return [], 0
    lines = textwrap.wrap(text, 70)[:3]
    out = [f'<path d="M4 6 l10 -4 l4 4 l-10 10 l-5 1 z" fill="{c["accent"]}"/>']
    out += [_text(26, 16 + i * 21, line, KID, size=16, fill=c["ink"], weight=700, anchor="start")
            for i, line in enumerate(lines)]
    return out, 12 + 21 * len(lines)


def _split(word: str, syllable: str) -> tuple[str, str, str]:
    """word = before + syllable + after, matching without accents (folding keeps the length)."""
    i = _fold(word).find(_fold(syllable).strip())
    if i < 0:
        return word, "", ""
    n = len(syllable)
    return word[:i], word[i:i + n], word[i + n:]


def _tspans(parts: list[tuple[str, str]]) -> str:
    return "".join(f'<tspan fill="{fill}">{escape(s)}</tspan>' for s, fill in parts if s)


def _word(x, y, parts, *, size, weight=700, anchor="middle", font=KID) -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-family="{font}" font-size="{size}" '
            f'font-weight="{weight}">{_tspans(parts)}</text>')


def _guides(x, y, w, c) -> str:
    """School guide lines: top, dashed middle, baseline."""
    return (f'<line x1="{x}" x2="{x + w}" y1="{y}" y2="{y}" stroke="{c["line"]}" stroke-width="1"/>'
            f'<line x1="{x}" x2="{x + w}" y1="{y + 14}" y2="{y + 14}" stroke="{c["line"]}" stroke-dasharray="4 4"/>'
            f'<line x1="{x}" x2="{x + w}" y1="{y + 28}" y2="{y + 28}" stroke="{c["muted"]}" stroke-width="1.4"/>')


def _box(x, y, w, h, c, *, dashed=False, fill="none", rx=10) -> str:
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" '
            f'stroke="{c["ink"]}" stroke-width="1.6"{dash}/>')


def _rng(block) -> random.Random:
    return random.Random(f"{block.id}:{block.model_dump_json(exclude={'pictures'})}")  # same tome, same page


def _fit(room: float, rows: int, lo: float, hi: float) -> float:
    """Row height that spreads `rows` over the room left on the page, within sensible limits."""
    return max(lo, min(hi, room / max(rows, 1)))


# --- syllable chart -----------------------------------------------------------------------------------------

def syllable_chart(b, c, font, pic, top, room):
    letter = b.letter.strip()
    body = [_box(0, top, W, 104, c, fill=c["soft"], rx=14),
            _text(76, top + 82, f"{letter[:1].upper()}{letter[1:]} {letter.lower()}", KID, size=76,
                  fill=c["accent"], weight=800)]
    syllables = list(dict.fromkeys(w.syllable for w in b.words))
    body += [_text(212 + i * 88, top + 66, s, KID, size=36, fill=c["ink"], weight=700)
             for i, s in enumerate(syllables[:5])]
    cols = 3 if len(b.words) > 8 else 2
    rows = -(-len(b.words) // cols)
    cw, y0 = W / cols, top + 116
    ch = _fit(room - 116, rows, 110, 190)
    p = min(ch - 20, cw * 0.55)
    for i, w in enumerate(b.words):
        x, y = (i % cols) * cw, y0 + (i // cols) * ch
        before, syl, after = _split(w.word, w.syllable)
        body.append(f'<rect x="{x + 3:.1f}" y="{y:.1f}" width="{cw - 6:.1f}" height="{ch - 8:.1f}" rx="12" fill="none" '
                    f'stroke="{c["ink"]}" stroke-width="1.6"/>')
        body.append(_word(x + 16, y + 34, [(before, c["ink"]), (syl, c["accent"]), (after, c["ink"])], size=24,
                          anchor="start"))
        body.append(_text(x + 16, y + ch - 24, w.syllable, KID, size=40, fill=c["accent"], weight=700, anchor="start"))
        body.append(pic(w.word, x + cw - p - 12, y + (ch - 8 - p) / 2, p, p))
    return W, y0 + rows * ch, body


# --- picture words ------------------------------------------------------------------------------------------

def picture_words(b, c, font, pic, top, room):
    return {"write": _pw_write, "complete": _pw_complete, "circle": _pw_circle, "match": _pw_match}[b.mode](
        b, c, font, pic, top, room)


def _pw_write(b, c, font, pic, top, room):
    cols = 3 if len(b.items) in (3, 5, 6, 9) else 2 if len(b.items) <= 4 else 4
    rows = -(-len(b.items) // cols)
    cw = W / cols
    ch = _fit(room, rows, 170, min(380, cw + 50))
    p = min(cw - 30, ch - 70)
    body = []
    for i, item in enumerate(b.items):
        x, y = (i % cols) * cw, top + (i // cols) * ch
        body.append(_box(x + 6, y + 4, cw - 12, ch - 12, c, rx=14))
        body.append(pic(item.word, x + (cw - p) / 2, y + 12, p, p))
        body.append(_guides(x + 18, y + ch - 52, cw - 36, c))
    return W, top + rows * ch, body


def _pw_complete(b, c, font, pic, top, room):
    rows = -(-len(b.items) // 2)
    cw, ch, body = W / 2, _fit(room, rows, 130, 300), []
    p = min(ch - 64, 220)
    for i, item in enumerate(b.items):
        x, y = (i % 2) * cw, top + (i // 2) * ch
        before, syl, after = _split(item.word, item.syllable)
        body.append(_box(x + 6, y + 4, cw - 12, ch - 12, c, rx=14))
        body.append(pic(item.word, x + (cw - p) / 2, y + 10, p, p))
        size = 32
        char = size * 0.6
        bw = 22 + char * len(syl)
        total = char * (len(before) + len(after)) + bw + 12
        tx, ty = x + (cw - total) / 2, y + ch - 26
        body.append(_word(tx, ty, [(before, c["ink"])], size=size, anchor="start"))
        bx = tx + char * len(before) + (6 if before else 0)
        body.append(f'<rect class="blank" x="{bx:.1f}" y="{ty - 32:.1f}" width="{bw:.1f}" height="42" rx="6" '
                    f'fill="#fff" stroke="{c["accent"]}" stroke-width="2.2"/>')
        body.append(_word(bx + bw + 6, ty, [(after, c["ink"])], size=size, anchor="start"))
    return W, top + rows * ch, body


def _pw_circle(b, c, font, pic, top, room):
    rng, pool = _rng(b), list(dict.fromkeys(i.syllable for i in b.items))
    pool += [s for s in ("ma", "pa", "sa", "la", "me", "pi", "so", "lu") if s not in pool]
    rows = -(-len(b.items) // 2)
    cw, ch, body = W / 2, _fit(room, rows, 140, 280), []
    p = min(ch - 24, 170)
    for i, item in enumerate(b.items):
        x, y = (i % 2) * cw, top + (i // 2) * ch
        options = [item.syllable] + rng.sample([s for s in pool if s != item.syllable], 2)
        rng.shuffle(options)
        body.append(_box(x + 6, y + 4, cw - 12, ch - 12, c, rx=14))
        body.append(pic(item.word, x + 16, y + (ch - 8 - p) / 2, p, p))
        gap = (ch - 30) / 3
        for k, s in enumerate(options):
            oy = y + 12 + gap * (k + 0.5)
            body.append(f'<ellipse cx="{x + cw - 70:.1f}" cy="{oy:.1f}" rx="46" ry="{min(22, gap / 2 - 3):.1f}" '
                        f'fill="none" stroke="{c["ink"]}" stroke-width="1.6"/>')
            body.append(_text(x + cw - 70, oy + 10, s, KID, size=28, fill=c["ink"], weight=700))
    return W, top + rows * ch, body


def _pw_match(b, c, font, pic, top, room):
    syllables = [i.syllable for i in b.items]
    _rng(b).shuffle(syllables)
    rh, body = _fit(room, len(b.items), 100, 200), []
    p = rh - 16
    for i, item in enumerate(b.items):
        y = top + i * rh
        body.append(pic(item.word, 30, y + 8, p, p))
        body.append(f'<circle cx="{50 + p:.1f}" cy="{y + rh / 2:.1f}" r="7" fill="{c["ink"]}"/>')
        body.append(f'<circle cx="430" cy="{y + rh / 2:.1f}" r="7" fill="{c["ink"]}"/>')
        body.append(_box(460, y + rh / 2 - 34, 150, 68, c, rx=14))
        body.append(_text(535, y + rh / 2 + 14, syllables[i], KID, size=40, fill=c["accent"], weight=700))
    return W, top + len(b.items) * rh, body


# --- cut-out cards ------------------------------------------------------------------------------------------

def syllable_cards(b, c, font, pic, top, room):
    cols = 6 if len(b.syllables) > 24 else 5 if len(b.syllables) > 12 else 4
    rows = -(-len(b.syllables) // cols)
    cw, ch, body = W / cols, _fit(room, rows, 70, 140), []
    for i, s in enumerate(b.syllables):
        x, y = (i % cols) * cw, top + (i // cols) * ch
        body.append(_box(x + 3, y + 3, cw - 6, ch - 6, c, dashed=b.cut, rx=6))
        body.append(_text(x + cw / 2, y + ch / 2 + 15, s, KID, size=min(44, ch * 0.45), fill=c["ink"], weight=700))
    return W, top + rows * ch, body


# --- reading and dictation ----------------------------------------------------------------------------------

def _band(title, y, c, font) -> list[str]:
    return [f'<rect x="0" y="{y}" width="{W}" height="50" rx="12" fill="{c["tint"]}"/>',
            _text(W / 2, y + 35, title, font, size=28, fill=c["ink"], weight=800)]


def reading(b, c, font, pic, top, room):
    body = _band(b.title or "Practiquemos la lectura", top, c, font)
    wrapped = [textwrap.wrap(line.text, 24 if line.picture else 31)[:3] for line in b.sentences]
    extra = 40 if b.rubric else 0
    unit = _fit(room - 64 - extra, sum(len(w) + 1 for w in wrapped), 36, 80)
    y = top + 66
    for i, (line, lines) in enumerate(zip(b.sentences, wrapped)):
        rh = unit * (len(lines) + 1)
        body.append(_box(0, y, W, rh - 10, c, rx=12))
        body.append(_text(22, y + unit, f"{i + 1}.", font, size=28, fill=c["accent"], weight=800, anchor="start"))
        body += [_text(58, y + unit * (k + 1), t, KID, size=30, fill=c["ink"], weight=400, anchor="start")
                 for k, t in enumerate(lines)]
        if line.picture:
            body.append(pic(line.picture, W - 190, y + 6, 110, rh - 22))
        if b.rubric:
            body.append(f'<rect x="{W - 62}" y="{y + (rh - 10) / 2 - 20:.1f}" width="40" height="40" rx="5" '
                        f'fill="#fff" stroke="{c["ink"]}" stroke-width="1.8"/>')
        y += rh
    if b.rubric:
        body.append(_text(W / 2, y + 24, "Logrado = L     Logrado con ayuda = LA     No logrado = NL", KID, size=16,
                          fill=c["muted"], weight=400))
        y += extra
    return W, y, body


def dictation(b, c, font, pic, top, room):
    body = _band(b.title or "Dictado", top, c, font)
    y = top + 62
    if b.show_words and b.words:
        half = -(-len(b.words) // 2)
        body.append(f'<rect x="0" y="{y}" width="{W}" height="{28 + 28 * half}" rx="12" fill="{c["soft"]}"/>')
        body.append(_text(16, y + 22, "Para el adulto:", KID, size=14, fill=c["muted"], weight=700, anchor="start"))
        for i, w in enumerate(b.words):
            x, yy = 44 + (i // half) * (W / 2), y + 48 + (i % half) * 28
            body.append(_text(x, yy, f"{i + 1}. {w}", KID, size=20, fill=c["ink"], weight=400, anchor="start"))
        y += 42 + 28 * half
    gap = _fit(room - (y - top), b.lines, 46, 100)
    for i in range(b.lines):
        yy = y + i * gap
        body.append(_text(10, yy + gap - 12, f"{i + 1}.", font, size=24, fill=c["accent"], weight=800, anchor="start"))
        body.append(_guides(52, yy + gap - 40, W - 62, c))
    return W, y + b.lines * gap + 8, body


def fill_sentences(b, c, font, pic, top, room):
    rh, body, y = _fit(room, len(b.items), 100, 230), [], top
    for i, item in enumerate(b.items):
        before, _, after = item.text.partition("___")
        body.append(_box(0, y, W, rh - 12, c, rx=12))
        body.append(_text(20, y + rh / 2 + 4, f"{i + 1}.", font, size=28, fill=c["accent"], weight=800, anchor="start"))
        parts = (f'<tspan>{escape(before.rstrip())} </tspan><tspan fill="{c["muted"]}">________</tspan>'
                 f'<tspan> {escape(after.lstrip())}</tspan>')
        body.append(f'<text x="58" y="{y + rh / 2 + 4:.1f}" font-family="{KID}" font-size="30" fill="{c["ink"]}">'
                    f'{parts}</text>')
        p = rh - 28
        body.append(pic(item.answer, W - p - 16, y + 8, p, p))
        y += rh
    return W, y, body


# --- word search, classify, frames --------------------------------------------------------------------------

def search_grid(b) -> list[list[str]]:
    """Words across or down (no diagonals for young readers); the rest filled with the words' own letters."""
    rng, n = _rng(b), b.size
    grid = [["" for _ in range(n)] for _ in range(n)]
    for word in sorted((_fold(w).replace(" ", "").upper() for w in b.words), key=len, reverse=True):
        for _ in range(200):
            down = rng.random() < 0.4
            span = n - len(word) + 1
            r, col = (rng.randrange(span), rng.randrange(n)) if down else (rng.randrange(n), rng.randrange(span))
            cells = [(r + k, col) if down else (r, col + k) for k in range(len(word))]
            if all(grid[i][j] in ("", word[k]) for k, (i, j) in enumerate(cells)):
                for k, (i, j) in enumerate(cells):
                    grid[i][j] = word[k]
                break
    letters = sorted({ch for w in b.words for ch in _fold(w).replace(" ", "").upper()})
    return [[cell or rng.choice(letters) for cell in row] for row in grid]


def word_search(b, c, font, pic, top, room):
    n, k = b.size, len(b.words)
    per_row = 4 if k > 4 else k
    clue_rows = -(-k // per_row)
    clue_w, p = W / per_row, 96
    body = []
    for i, w in enumerate(b.words):
        x, y = (i % per_row) * clue_w, top + (i // per_row) * (p + 34)
        body.append(pic(w, x + (clue_w - p) / 2, y, p, p))
        body.append(_text(x + clue_w / 2, y + p + 24, w, KID, size=20, fill=c["ink"], weight=700))
    y0 = top + clue_rows * (p + 34) + 16
    cell = max(30, min(60, (room - (y0 - top) - 16) / n, (W - 20) / n))
    x0 = (W - cell * n) / 2
    body.append(_box(x0 - 8, y0 - 8, cell * n + 16, cell * n + 16, c, rx=10))
    for r, row in enumerate(search_grid(b)):
        for j, ch in enumerate(row):
            body.append(_text(x0 + j * cell + cell / 2, y0 + r * cell + cell * 0.7, ch, KID, size=cell * 0.6,
                              fill=c["ink"], weight=700))
    return W, y0 + cell * n + 12, body


def classify(b, c, font, pic, top, room):
    cols = len(b.columns)
    cw, body = W / cols, []
    per = 4
    bank_h = 32 + -(-len(b.words) // per) * 44
    rows = -(-len(b.words) // cols) + 1
    gap = _fit(room - 80 - bank_h - 20, rows, 44, 64)
    for i, s in enumerate(b.columns):
        x = i * cw
        body.append(_box(x + 6, top, cw - 12, 60, c, fill=c["tint"], rx=12))
        body.append(_text(x + cw / 2, top + 44, s, KID, size=36, fill=c["ink"], weight=700))
        body.append(_box(x + 6, top + 68, cw - 12, rows * gap + 10, c, rx=12))
        body += [f'<line x1="{x + 20:.1f}" x2="{x + cw - 20:.1f}" y1="{top + 68 + (r + 1) * gap:.1f}" '
                 f'y2="{top + 68 + (r + 1) * gap:.1f}" stroke="{c["muted"]}" stroke-width="1.2"/>' for r in range(rows)]
    y = top + 68 + rows * gap + 26
    words = list(b.words)
    _rng(b).shuffle(words)
    body.append(_box(0, y, W, bank_h, c, dashed=True, rx=12))
    for i, w in enumerate(words):
        body.append(_text((i % per) * (W / per) + W / per / 2, y + 40 + (i // per) * 44, w, KID, size=26,
                          fill=c["ink"], weight=400))
    return W, y + bank_h + 4, body


def draw_frames(b, c, font, pic, top, room):
    cols = 1 if b.count <= 3 else 2
    rows = -(-b.count // cols)
    cw, ch, body = W / cols, _fit(room, rows, 200, 520), []
    for i in range(b.count):
        x, y = (i % cols) * cw, top + (i // cols) * ch
        body.append(_box(x + 8, y + 4, cw - 16, ch - 40, c, rx=16))
        body.append(f'<rect x="{x + 15:.1f}" y="{y + 11}" width="{cw - 30:.1f}" height="{ch - 54:.1f}" rx="11" '
                    f'fill="none" stroke="{c["tint"]}" stroke-width="5"/>')
        if i < len(b.labels) and b.labels[i]:
            body.append(_text(x + cw / 2, y + ch - 10, b.labels[i], KID, size=20, fill=c["ink"], weight=700))
    return W, top + rows * ch, body
