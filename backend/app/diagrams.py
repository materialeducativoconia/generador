"""Diagrams drawn by code (no AI): staff, timeline, cycle, bar chart, number line, fractions, clock.

Each renderer returns one inline <svg> in the tome's colours and heading font. The same markup prints in
the PDF and shows in the web preview, so the two never drift. WeasyPrint rules: sizes in px, no `opacity`
attribute on the <svg>, every string from the model escaped.
"""

import math
import textwrap
from html import escape

from markupsafe import Markup

NOTE_NAMES_ES = {"C": "Do", "D": "Re", "E": "Mi", "F": "Fa", "G": "Sol", "A": "La", "B": "Si"}
MUSIC = "'Noto Music'"
BEATS = {"whole": 4, "half": 2, "quarter": 1, "eighth": 0.5}


def render_diagram(block, c: dict, font: str) -> Markup:
    draw = {"staff": staff, "timeline": timeline, "cycle": cycle, "bar_chart": bar_chart,
            "number_line": number_line, "fraction": fraction, "clock": clock}[block.type]
    return Markup(draw(block, c, f"'{font}', Nunito, {MUSIC}, sans-serif"))


def _svg(kind: str, w: float, h: float, body: list[str]) -> str:
    return (f'<svg class="dg dg-{kind}" viewBox="0 0 {w:g} {h:g}" width="{w:g}px" height="{h:g}px" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(body)}</svg>')


def _text(x, y, s, font, *, size=13, fill, weight=600, anchor="middle", family=None, cls=None) -> str:
    c = f' class="{cls}"' if cls else ""
    return (f'<text{c} x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-family="{family or font}" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}">{escape(str(s))}</text>')


def _lines(x, y, lines: list[str], font, *, size=13, fill, weight=600, anchor="middle", lead=1.25) -> str:
    """Several centred lines starting at baseline y."""
    return "".join(_text(x, y + i * size * lead, line, font, size=size, fill=fill, weight=weight, anchor=anchor)
                   for i, line in enumerate(lines))


def _wrap(s: str, width: int, max_lines: int = 3) -> list[str]:
    lines = textwrap.wrap(s, width=max(width, 4)) or [s]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(width - 1, 1)].rstrip() + "…"
    return lines


def _arrowhead(x, y, angle, size, fill) -> str:
    """A filled triangle with its tip at (x, y) pointing along `angle` (radians)."""
    a1, a2 = angle + math.radians(152), angle - math.radians(152)
    pts = [(x, y), (x + size * math.cos(a1), y + size * math.sin(a1)), (x + size * math.cos(a2), y + size * math.sin(a2))]
    return f'<polygon points="{" ".join(f"{px:.1f},{py:.1f}" for px, py in pts)}" fill="{fill}"/>'


# --- staff -----------------------------------------------------------------------------------------------

def _step(pitch: str) -> int:
    return int(pitch[-1]) * 7 + "CDEFGAB".index(pitch[0])


def staff(b, c, font) -> str:
    s, top = 12, 46  # line spacing, top line
    bottom = top + 4 * s
    ref = 30 if b.clef == "treble" else 18  # E4 / G2 sit on the bottom line
    head_x = 112 if b.time else 74
    gap = 50
    w = head_x + gap * len(b.notes) + 10
    h = bottom + (52 if b.show_names else 30)
    ink = c["ink"]
    body = [f'<line x1="6" x2="{w - 6}" y1="{top + i * s}" y2="{top + i * s}" stroke="{ink}" stroke-width="1.2"/>'
            for i in range(5)]
    if b.clef == "treble":
        body.append(_text(10, bottom - s + 1, "\U0001D11E", font, size=s * 6.3, fill=ink, weight=400, anchor="start",
                          family=MUSIC))
    else:
        body.append(_text(10, top + s + 1, "\U0001D122", font, size=s * 3.6, fill=ink, weight=400, anchor="start",
                          family=MUSIC))
    if b.time:
        upper, lower = b.time.split("/")
        body.append(_text(86, top + 2 * s - 1, upper, font, size=s * 2.1, fill=ink, weight=800))
        body.append(_text(86, bottom - 1, lower, font, size=s * 2.1, fill=ink, weight=800))
    per_bar = int(b.time.split("/")[0]) if b.time else None
    beats = 0.0
    for i, note in enumerate(b.notes):
        x = head_x + gap * i + gap / 2
        if note.pitch == "rest":
            body.append(_rest(x, top, s, note.duration, ink))
        else:
            body.append(_note(x, bottom, s, ref, note.pitch, note.duration, ink, c["accent"]))
            if b.show_names:
                name = NOTE_NAMES_ES[note.pitch[0]] + ("♯" if "#" in note.pitch else "")
                body.append(_text(x, h - 10, name, font, size=13, fill=c["muted"], weight=700))
        beats += BEATS[note.duration]
        if per_bar and i < len(b.notes) - 1 and beats % per_bar == 0:
            bx = x + gap / 2
            body.append(f'<line class="bar" x1="{bx}" x2="{bx}" y1="{top}" y2="{bottom}" stroke="{ink}" stroke-width="1.4"/>')
    body.append(f'<line class="bar" x1="{w - 12}" x2="{w - 12}" y1="{top}" y2="{bottom}" stroke="{ink}" stroke-width="1.4"/>')
    body.append(f'<rect x="{w - 9}" y="{top}" width="3.5" height="{4 * s}" fill="{ink}"/>')
    return _svg("staff", w, h, body)


def _note(x, bottom, s, ref, pitch, duration, ink, accent) -> str:
    step = _step(pitch)
    y = bottom - (step - ref) * s / 2
    out = []
    for ledger in list(range(ref - 2, step - 1, -2)) + list(range(ref + 10, step + 1, 2)):  # below / above the staff
        ly = bottom - (ledger - ref) * s / 2
        out.append(f'<line x1="{x - 11}" x2="{x + 11}" y1="{ly}" y2="{ly}" stroke="{ink}" stroke-width="1.2"/>')
    if "#" in pitch:
        out.append(_text(x - 17, y + 5, "♯", "", size=17, fill=ink, weight=400, family=MUSIC))
    hollow = duration in ("whole", "half")
    rx = 7.6 if duration == "whole" else 6.6
    fill = "#ffffff" if hollow else ink
    out.append(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="4.9" transform="rotate(-20 {x} {y})" fill="{fill}" '
               f'stroke="{ink}" stroke-width="{2 if hollow else 1}"/>')
    if duration != "whole":
        up = step < ref + 4  # below the middle line: stem up
        sx, sy2 = (x + 6, y - 3.4 * s) if up else (x - 6, y + 3.4 * s)
        out.append(f'<line x1="{sx}" x2="{sx}" y1="{y}" y2="{sy2}" stroke="{ink}" stroke-width="1.4"/>')
        if duration == "eighth":
            d = 1 if up else -1
            out.append(f'<path d="M{sx} {sy2} q 2 {7 * d} 10 {12 * d} q 4 {6 * d} -1 {14 * d}" fill="none" '
                       f'stroke="{ink}" stroke-width="2"/>')
    return "".join(out)


def _rest(x, top, s, duration, ink) -> str:
    if duration == "whole":  # hangs from the fourth line
        return f'<rect x="{x - 7}" y="{top + s}" width="14" height="{s / 2}" fill="{ink}"/>'
    if duration == "half":  # sits on the middle line
        return f'<rect x="{x - 7}" y="{top + 1.5 * s}" width="14" height="{s / 2}" fill="{ink}"/>'
    glyph = "\U0001D13D" if duration == "quarter" else "\U0001D13E"
    return _text(x, top + 3 * s, glyph, "", size=s * 3.6, fill=ink, weight=400, family=MUSIC)


# --- timeline --------------------------------------------------------------------------------------------

def timeline(b, c, font) -> str:
    n = len(b.events)
    if n > 6:
        return _vertical_timeline(b, c, font)
    w, line_y = 640, 62
    inset = min((w - 40) / (2 * (n - 1)), 90)  # room for half a label beyond the first and last dot
    gap = (w - 2 * inset) / (n - 1)
    body = [f'<line x1="24" x2="{w - 24}" y1="{line_y}" y2="{line_y}" stroke="{c["line"]}" stroke-width="5" '
            f'stroke-linecap="round"/>', _arrowhead(w - 12, line_y, 0, 14, c["line"])]
    width_chars = int(min(gap, 2 * inset) / 7.2)
    tallest = 0
    for i, e in enumerate(b.events):
        x = inset + gap * i
        body.append(f'<circle cx="{x:.1f}" cy="{line_y}" r="9" fill="{c["accent"]}" stroke="#ffffff" stroke-width="3"/>')
        body.append(_text(x, line_y - 22, e.when, font, size=15, fill=c["accent"], weight=800))
        lines = _wrap(e.label, width_chars, 4)
        tallest = max(tallest, len(lines))
        body.append(_lines(x, line_y + 34, lines, font, size=12.5, fill=c["ink"]))
    return _svg("timeline", w, line_y + 34 + tallest * 16 + 6, body)


def _vertical_timeline(b, c, font) -> str:
    w, row, x = 600, 44, 132
    h = row * len(b.events) + 16
    body = [f'<line x1="{x}" x2="{x}" y1="12" y2="{h - 12}" stroke="{c["line"]}" stroke-width="5" stroke-linecap="round"/>']
    for i, e in enumerate(b.events):
        y = 26 + row * i
        body.append(f'<circle cx="{x}" cy="{y}" r="8" fill="{c["accent"]}" stroke="#ffffff" stroke-width="3"/>')
        body.append(_text(x - 20, y + 5, e.when, font, size=14, fill=c["accent"], weight=800, anchor="end"))
        body.append(_text(x + 22, y + 5, _wrap(e.label, 56, 1)[0], font, size=13, fill=c["ink"], anchor="start"))
    return _svg("timeline", w, h, body)


# --- cycle / process -------------------------------------------------------------------------------------

BOX_W, BOX_H = 148, 62


def _box(x, y, label, n, c, font) -> str:
    """A rounded step box centred on (x, y) with its number badge."""
    lines = _wrap(label, 17, 3)
    size = 13 if len(lines) < 3 else 11.5
    first = y - (len(lines) - 1) * size * 1.25 / 2 + size * 0.36
    return (f'<rect x="{x - BOX_W / 2:.1f}" y="{y - BOX_H / 2:.1f}" width="{BOX_W}" height="{BOX_H}" rx="14" '
            f'fill="{c["soft"]}" stroke="{c["accent"]}" stroke-width="2"/>'
            f'<circle cx="{x - BOX_W / 2 + 4:.1f}" cy="{y - BOX_H / 2 + 4:.1f}" r="12" fill="{c["accent"]}"/>'
            + _text(x - BOX_W / 2 + 4, y - BOX_H / 2 + 8.5, n, font, size=12, fill="#ffffff", weight=800)
            + _lines(x, first, lines, font, size=size, fill=c["ink"], weight=700))


def cycle(b, c, font) -> str:
    return _closed_cycle(b, c, font) if b.closed else _process(b, c, font)


def _closed_cycle(b, c, font) -> str:
    n = len(b.steps)
    rx, ry = (190, 150) if n > 4 else (170, 120)
    w, h = 2 * rx + BOX_W + 20, 2 * ry + BOX_H + 30
    cx, cy = w / 2, h / 2
    angles = [-math.pi / 2 + 2 * math.pi * i / n for i in range(n)]
    pos = [(cx + rx * math.cos(a), cy + ry * math.sin(a)) for a in angles]
    body = []
    for i in range(n):  # arrows first, boxes on top
        a0, a1 = angles[i], angles[i] + 2 * math.pi / n
        span = a1 - a0
        start, end = a0 + span * 0.3, a1 - span * 0.3
        pts = [(cx + rx * math.cos(start + (end - start) * t / 12), cy + ry * math.sin(start + (end - start) * t / 12))
               for t in range(13)]
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        body.append(f'<path d="{d}" fill="none" stroke="{c["accent"]}" stroke-width="3" stroke-linecap="round"/>')
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        body.append(_arrowhead(x2, y2, math.atan2(y2 - y1, x2 - x1), 13, c["accent"]))
    for i, (x, y) in enumerate(pos):
        body.append(_box(x, y, b.steps[i], i + 1, c, font))
    return _svg("cycle", w, h, body)


def _process(b, c, font) -> str:
    """Rows of up to four steps, snaking so every arrow is short and straight."""
    per_row, gx, gy = 4 if len(b.steps) > 3 else len(b.steps), 40, 46
    rows = math.ceil(len(b.steps) / per_row)
    w = per_row * BOX_W + (per_row - 1) * gx + 24
    h = rows * BOX_H + (rows - 1) * gy + 24
    centres = []
    for i in range(len(b.steps)):
        r, k = divmod(i, per_row)
        col = k if r % 2 == 0 else per_row - 1 - k
        centres.append((12 + BOX_W / 2 + col * (BOX_W + gx), 12 + BOX_H / 2 + r * (BOX_H + gy)))
    body = []
    for (x1, y1), (x2, y2) in zip(centres, centres[1:]):
        if y1 == y2:
            d = 1 if x2 > x1 else -1
            sx, ex = x1 + d * (BOX_W / 2 + 6), x2 - d * (BOX_W / 2 + 6)
            body.append(f'<line x1="{sx:.1f}" x2="{ex - d * 8:.1f}" y1="{y1:.1f}" y2="{y1:.1f}" stroke="{c["accent"]}" '
                        f'stroke-width="3"/>')
            body.append(_arrowhead(ex, y1, 0 if d > 0 else math.pi, 13, c["accent"]))
        else:
            sy, ey = y1 + BOX_H / 2 + 5, y2 - BOX_H / 2 - 5
            body.append(f'<line x1="{x1:.1f}" x2="{x1:.1f}" y1="{sy:.1f}" y2="{ey - 8:.1f}" stroke="{c["accent"]}" '
                        f'stroke-width="3"/>')
            body.append(_arrowhead(x1, ey, math.pi / 2, 13, c["accent"]))
    for i, (x, y) in enumerate(centres):
        body.append(_box(x, y, b.steps[i], i + 1, c, font))
    return _svg("process", w, h, body)


# --- bar chart -------------------------------------------------------------------------------------------

def _nice_max(v: float) -> float:
    if v <= 0:
        return 1
    mag = 10 ** math.floor(math.log10(v))
    return next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= v)


def _num(v: float) -> str:
    return f"{v:g}".replace(".", ",")  # Spanish decimal comma


def bar_chart(b, c, font) -> str:
    n = len(b.values)
    left, top, plot_h = 52, 28, 210
    slot = min(96, 540 / n)
    w = left + slot * n + 16
    top_v = _nice_max(max(b.values))
    labels = [_wrap(lb, int(slot / 7.5), 2) for lb in b.labels]
    h = top + plot_h + 18 + max(len(x) for x in labels) * 15 + 4
    base = top + plot_h
    body = []
    for k in range(5):
        v = top_v * k / 4
        y = base - plot_h * k / 4
        body.append(f'<line x1="{left}" x2="{w - 8}" y1="{y:.1f}" y2="{y:.1f}" stroke="{c["line"]}" stroke-width="1"/>')
        body.append(_text(left - 8, y + 4, _num(round(v, 2)), font, size=11, fill=c["muted"], anchor="end"))
    if b.unit:
        body.append(_text(left - 8, top - 12, b.unit, font, size=11, fill=c["muted"], weight=700, anchor="start"))
    for i, (v, lines) in enumerate(zip(b.values, labels)):
        x = left + slot * i + slot * 0.18
        bw, bh = slot * 0.64, plot_h * v / top_v
        body.append(f'<rect x="{x:.1f}" y="{base - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="4" fill="{c["accent"]}"/>')
        body.append(_text(x + bw / 2, base - bh - 6, _num(v), font, size=12, fill=c["ink"], weight=800))
        body.append(_lines(x + bw / 2, base + 18, lines, font, size=12, fill=c["ink"]))
    body.append(f'<line x1="{left}" x2="{w - 8}" y1="{base}" y2="{base}" stroke="{c["ink"]}" stroke-width="1.6"/>')
    return _svg("bar", w, h, body)


# --- number line -----------------------------------------------------------------------------------------

def number_line(b, c, font) -> str:
    values = list(range(b.start, b.end + 1, b.step))
    w, y = 640, 40
    gap = (w - 70) / max(len(values) - 1, 1)
    marks, blanks = set(b.marks), set(b.blanks)
    body = [f'<line x1="14" x2="{w - 14}" y1="{y}" y2="{y}" stroke="{c["ink"]}" stroke-width="2"/>',
            _arrowhead(w - 6, y, 0, 12, c["ink"]), _arrowhead(6, y, math.pi, 12, c["ink"])]
    for i, v in enumerate(values):
        x = 35 + gap * i
        body.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y - 9}" y2="{y + 9}" stroke="{c["ink"]}" stroke-width="2"/>')
        if v in marks:
            body.append(f'<circle cx="{x:.1f}" cy="{y}" r="8" fill="{c["accent"]}"/>')
        if v in blanks:
            bw = min(gap - 4, 34)
            body.append(f'<rect class="blank" x="{x - bw / 2:.1f}" y="{y + 16}" width="{bw:.1f}" height="26" rx="5" '
                        f'fill="#ffffff" stroke="{c["accent"]}" stroke-width="1.6"/>')
        else:
            body.append(_text(x, y + 36, v, font, size=15 if len(values) < 16 else 12,
                              fill=c["accent"] if v in marks else c["ink"], weight=800 if v in marks else 600))
    return _svg("numberline", w, y + 50, body)


# --- fractions -------------------------------------------------------------------------------------------

def fraction(b, c, font) -> str:
    cell = 170 if b.shape == "circle" else 220
    label_h = 64 if b.show_label else 8
    shape_h = 140 if b.shape == "circle" else 54
    w, h = cell * len(b.fractions), shape_h + label_h + 12
    body = []
    for i, f in enumerate(b.fractions):
        cx = cell * i + cell / 2
        on = (lambda k: b.shaded and k < f.numerator)
        if b.shape == "circle":
            r, cy = 64, 74
            if f.denominator == 1:
                body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{c["accent"] if on(0) else "#ffffff"}" '
                            f'stroke="{c["ink"]}" stroke-width="2.4"/>')
            for k in range(f.denominator if f.denominator > 1 else 0):
                a0 = -math.pi / 2 + 2 * math.pi * k / f.denominator
                a1 = a0 + 2 * math.pi / f.denominator
                large = 1 if a1 - a0 > math.pi else 0
                d = (f"M{cx} {cy} L{cx + r * math.cos(a0):.2f} {cy + r * math.sin(a0):.2f} "
                     f"A{r} {r} 0 {large} 1 {cx + r * math.cos(a1):.2f} {cy + r * math.sin(a1):.2f} Z")
                body.append(f'<path d="{d}" fill="{c["accent"] if on(k) else "#ffffff"}" stroke="{c["ink"]}" '
                            f'stroke-width="2.4" stroke-linejoin="round"/>')
        else:
            bw, top = cell - 30, 10
            part = bw / f.denominator
            for k in range(f.denominator):
                body.append(f'<rect x="{cx - bw / 2 + part * k:.1f}" y="{top}" width="{part:.1f}" height="44" '
                            f'fill="{c["accent"] if on(k) else "#ffffff"}" stroke="{c["ink"]}" stroke-width="2.4"/>')
        if b.show_label:
            ly = shape_h + 30
            body.append(_text(cx, ly, f.numerator, font, size=22, fill=c["ink"], weight=800))
            body.append(f'<line x1="{cx - 16}" x2="{cx + 16}" y1="{ly + 8}" y2="{ly + 8}" stroke="{c["ink"]}" stroke-width="2.4"/>')
            body.append(_text(cx, ly + 32, f.denominator, font, size=22, fill=c["ink"], weight=800))
    return _svg("fraction", w, h, body)


# --- clock -----------------------------------------------------------------------------------------------

def clock(b, c, font) -> str:
    cell, r, cy = 180, 72, 90
    h = cy + r + (44 if b.show_time else 16)
    body = []
    for i, t in enumerate(b.times):
        hh, mm = (int(x) for x in t.split(":"))
        cx = cell * i + cell / 2
        body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff" stroke="{c["ink"]}" stroke-width="3.5"/>')
        for k in range(60):
            a = math.radians(k * 6 - 90)
            inner = r - (10 if k % 5 == 0 else 5)
            body.append(f'<line x1="{cx + inner * math.cos(a):.1f}" y1="{cy + inner * math.sin(a):.1f}" '
                        f'x2="{cx + (r - 2) * math.cos(a):.1f}" y2="{cy + (r - 2) * math.sin(a):.1f}" '
                        f'stroke="{c["ink"]}" stroke-width="{2.2 if k % 5 == 0 else 1}"/>')
        for k in range(1, 13):
            a = math.radians(k * 30 - 90)
            body.append(_text(cx + (r - 22) * math.cos(a), cy + (r - 22) * math.sin(a) + 5, k, font, size=14,
                              fill=c["ink"], weight=800))
        if b.show_hands:
            for cls, angle, length, width, colour in (
                    ("hour", (hh % 12 + mm / 60) * 30, r * 0.5, 5, c["ink"]),
                    ("minute", mm * 6, r - 9, 3.2, c["accent"])):
                a = math.radians(angle - 90)
                body.append(f'<line class="{cls}" x1="{cx}" y1="{cy}" x2="{cx + length * math.cos(a):.1f}" '
                            f'y2="{cy + length * math.sin(a):.1f}" stroke="{colour}" stroke-width="{width}" '
                            f'stroke-linecap="round"/>')
        body.append(f'<circle cx="{cx}" cy="{cy}" r="5" fill="{c["ink"]}"/>')
        if b.show_time:
            body.append(_text(cx, cy + r + 32, f"{hh}:{mm:02d}", font, size=18, fill=c["ink"], weight=800))
    return _svg("clock", cell * len(b.times), h, body)
