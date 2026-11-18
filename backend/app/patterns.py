"""Pattern pages drawn exactly by code, so a pattern book costs no image model: mandalas and tiles to colour (black
outlines on white, like a printed colouring book) and rows of strokes to trace (pre-writing practice). The Writer
(DeepSeek) only picks the kind, the motifs and the level of detail; everything here is deterministic vector art."""

import math

INK = "#1c1917"
GUIDE = "#a8a29e"
SIZE = 600
DETAIL = {"simple": (3, 3.2), "medium": (5, 2.2), "detailed": (7, 1.5)}  # rings, stroke width


def _f(v: float) -> str:
    return f"{v:.1f}"


def motif(name: str, cx: float, y0: float, y1: float, hw: float, inner: bool = False) -> str:
    """One motif pointing up, from its base at y0 to its tip at y1 (y1 < y0), half as wide as hw."""
    h, ym = y0 - y1, (y0 + y1) / 2
    if name == "petal":
        d = (f"M{_f(cx)} {_f(y0)}Q{_f(cx + hw * 1.25)} {_f(ym)} {_f(cx)} {_f(y1)}"
             f"Q{_f(cx - hw * 1.25)} {_f(ym)} {_f(cx)} {_f(y0)}Z")
    elif name == "leaf":
        d = (f"M{_f(cx)} {_f(y0)}C{_f(cx + hw * 1.3)} {_f(y0 - h * 0.2)} {_f(cx + hw * 0.6)} {_f(y1 + h * 0.15)} "
             f"{_f(cx)} {_f(y1)}C{_f(cx - hw * 0.6)} {_f(y1 + h * 0.15)} {_f(cx - hw * 1.3)} {_f(y0 - h * 0.2)} "
             f"{_f(cx)} {_f(y0)}ZM{_f(cx)} {_f(y0)}L{_f(cx)} {_f(y1 + h * 0.12)}")
    elif name == "drop":
        d = (f"M{_f(cx)} {_f(y1)}C{_f(cx + hw * 1.1)} {_f(ym)} {_f(cx + hw)} {_f(y0)} {_f(cx)} {_f(y0)}"
             f"C{_f(cx - hw)} {_f(y0)} {_f(cx - hw * 1.1)} {_f(ym)} {_f(cx)} {_f(y1)}Z")
    elif name == "heart":
        w = min(hw, h * 0.55)
        top = y1 + h * 0.3
        d = (f"M{_f(cx)} {_f(y0)}C{_f(cx + w * 1.1)} {_f(y0 - h * 0.45)} {_f(cx + w)} {_f(y1)} {_f(cx + w * 0.5)} "
             f"{_f(y1)}C{_f(cx + w * 0.15)} {_f(y1)} {_f(cx)} {_f(top - h * 0.1)} {_f(cx)} {_f(top)}"
             f"C{_f(cx)} {_f(top - h * 0.1)} {_f(cx - w * 0.15)} {_f(y1)} {_f(cx - w * 0.5)} {_f(y1)}"
             f"C{_f(cx - w)} {_f(y1)} {_f(cx - w * 1.1)} {_f(y0 - h * 0.45)} {_f(cx)} {_f(y0)}Z")
    elif name == "star":
        r = min(hw, h / 2)
        pts = []
        for k in range(10):
            a = -math.pi / 2 + k * math.pi / 5
            rr = r if k % 2 == 0 else r * 0.45
            pts.append(f"{_f(cx + rr * math.cos(a))} {_f(ym + rr * math.sin(a))}")
        d = "M" + "L".join(pts) + "Z"
    elif name == "circle":
        r = min(hw, h / 2) * 0.85
        d = (f"M{_f(cx - r)} {_f(ym)}a{_f(r)} {_f(r)} 0 1 0 {_f(2 * r)} 0a{_f(r)} {_f(r)} 0 1 0 {_f(-2 * r)} 0Z")
    elif name == "dot":
        r = min(hw, h / 2) * 0.4
        d = (f"M{_f(cx - r)} {_f(ym)}a{_f(r)} {_f(r)} 0 1 0 {_f(2 * r)} 0a{_f(r)} {_f(r)} 0 1 0 {_f(-2 * r)} 0Z")
    elif name == "triangle":
        d = f"M{_f(cx - hw)} {_f(y0)}L{_f(cx)} {_f(y1)}L{_f(cx + hw)} {_f(y0)}Z"
    elif name == "scallop":
        r = min(hw, h)
        d = f"M{_f(cx - r)} {_f(y0)}A{_f(r)} {_f(r)} 0 0 1 {_f(cx + r)} {_f(y0)}"
    else:  # diamond
        d = f"M{_f(cx)} {_f(y1)}L{_f(cx + hw)} {_f(ym)}L{_f(cx)} {_f(y0)}L{_f(cx - hw)} {_f(ym)}Z"
    out = f'<path d="{d}"/>'
    if inner and name in ("petal", "drop", "diamond", "heart", "triangle", "circle", "star"):
        shrink = 0.5
        out += motif(name, cx, y0 - h * 0.18, y1 + h * 0.3, hw * shrink)
    return out


def mandala(motifs: list[str], symmetry: int, detail: str) -> list[str]:
    rings, _ = DETAIL[detail]
    c, outer, core = SIZE / 2, SIZE / 2 - 8, 34
    band = (outer - core) / rings
    body = [f'<circle cx="{_f(c)}" cy="{_f(c)}" r="{_f(core)}"/>',
            motif("star" if detail != "simple" else "circle", c, c + core * 0.7, c - core * 0.7, core * 0.7)]
    for i in range(rings):
        a, b = core + i * band, core + (i + 1) * band
        n = symmetry * (2 if i >= rings / 2 and detail != "simple" else 1)
        mid = (a + b) / 2
        hw = min(math.pi * mid / n * 0.92, band * 0.75)
        name = motifs[i % len(motifs)]
        offset = 180 / n if i % 2 else 0  # alternate rings sit between the petals of the one inside
        shape = motif(name, c, c - a - band * 0.06, c - b + band * 0.1, hw, inner=detail == "detailed" and band > 30)
        for k in range(n):
            body.append(f'<g transform="rotate({_f(k * 360 / n + offset)} {_f(c)} {_f(c)})">{shape}</g>')
        if detail != "simple" or i == rings - 1:
            body.append(f'<circle cx="{_f(c)}" cy="{_f(c)}" r="{_f(b)}" fill="none"/>')
    return body


def tiles(motifs: list[str], detail: str) -> list[str]:
    cols = {"simple": 3, "medium": 4, "detailed": 6}[detail]
    cell = SIZE / cols
    body = [f'<rect x="2" y="2" width="{SIZE - 4}" height="{SIZE - 4}" rx="6"/>']
    for r in range(cols):
        for k in range(cols):
            x, y = k * cell, r * cell
            body.append(f'<rect x="{_f(x + 2)}" y="{_f(y + 2)}" width="{_f(cell - 4)}" height="{_f(cell - 4)}"/>')
            name = motifs[(r + k) % len(motifs)]
            cx, cy = x + cell / 2, y + cell / 2
            pad = cell * 0.14
            shape = motif(name, cx, cy + cell / 2 - pad, cy - cell / 2 + pad, cell / 2 - pad,
                          inner=detail != "simple")
            turn = 180 if (r + k) % 2 else 0
            body.append(f'<g transform="rotate({turn} {_f(cx)} {_f(cy)})">{shape}</g>')
            if detail != "simple":  # a quarter circle in each corner joins the tiles into one pattern
                q = cell * 0.18
                body.append(
                    f'<path fill="none" d="M{_f(x + 2)} {_f(y + 2 + q)}A{_f(q)} {_f(q)} 0 0 0 {_f(x + 2 + q)} {_f(y + 2)}'
                    f'M{_f(x + cell - 2 - q)} {_f(y + 2)}A{_f(q)} {_f(q)} 0 0 0 {_f(x + cell - 2)} {_f(y + 2 + q)}'
                    f'M{_f(x + cell - 2)} {_f(y + cell - 2 - q)}A{_f(q)} {_f(q)} 0 0 0 {_f(x + cell - 2 - q)} '
                    f'{_f(y + cell - 2)}M{_f(x + 2 + q)} {_f(y + cell - 2)}A{_f(q)} {_f(q)} 0 0 0 {_f(x + 2)} '
                    f'{_f(y + cell - 2 - q)}"/>')
    return body


def stroke_path(name: str, x0: float, x1: float, top: float, bottom: float, period: float) -> str:
    """A row of one pre-writing stroke between two guide lines."""
    h, ym = bottom - top, (top + bottom) / 2
    steps = max(1, int((x1 - x0) // period))
    p = (x1 - x0) / steps
    if name == "zigzag":
        pts = [f"{_f(x0 + i * p / 2)} {_f(bottom if i % 2 == 0 else top)}" for i in range(steps * 2 + 1)]
        return "M" + "L".join(pts)
    if name == "waves":
        d = f"M{_f(x0)} {_f(ym)}"
        for i in range(steps):
            x = x0 + i * p
            d += f"Q{_f(x + p / 4)} {_f(top)} {_f(x + p / 2)} {_f(ym)}Q{_f(x + 3 * p / 4)} {_f(bottom)} {_f(x + p)} {_f(ym)}"
        return d
    if name == "castle":
        d = f"M{_f(x0)} {_f(bottom)}"
        for i in range(steps):
            x = x0 + i * p
            d += f"L{_f(x)} {_f(top)}L{_f(x + p / 2)} {_f(top)}L{_f(x + p / 2)} {_f(bottom)}L{_f(x + p)} {_f(bottom)}"
        return d
    if name == "arches":
        r = p / 2
        d = f"M{_f(x0)} {_f(bottom)}"
        for i in range(steps):
            d += f"A{_f(r)} {_f(min(h, r * 1.6))} 0 0 1 {_f(x0 + (i + 1) * p)} {_f(bottom)}"
        return d
    if name == "steps":  # three stairs up, three down
        rise, run = h / 3, p / 6
        d, y = f"M{_f(x0)} {_f(bottom)}", bottom
        for i in range(steps * 6):
            y += -rise if i % 6 < 3 else rise
            x = x0 + i * run
            d += f"L{_f(x)} {_f(y)}L{_f(x + run)} {_f(y)}"
        return d
    # loops: a prolate trochoid, the cursive "e" chain
    b = h / 2
    a = min(p / (2 * math.pi), b / 2.2)  # b well above a: the curve crosses itself into loops
    steps = max(1, int((x1 - x0 - 2 * b) // (2 * math.pi * a)))
    a = (x1 - x0 - 2 * b) / (2 * math.pi * steps)  # the row's whole width
    pts = []
    n = steps * 24
    for i in range(n + 1):
        t = 2 * math.pi * steps * i / n
        pts.append(f"{_f(x0 + b + a * t - b * math.sin(t))} {_f(ym - b * math.cos(t))}")
    return "M" + "L".join(pts)


def trace(strokes: list[str], detail: str, c: dict) -> tuple[list[str], float]:
    period, height = {"simple": (110, 70), "medium": (80, 56), "detailed": (56, 42)}[detail]
    rows = strokes * (6 // len(strokes)) if len(strokes) < 6 else strokes[:6]
    gap = height + 34
    body = []
    for i, name in enumerate(rows[:6]):
        top = 14 + i * gap
        bottom = top + height
        body.append(f'<line x1="10" x2="590" y1="{_f(top)}" y2="{_f(top)}" stroke="{GUIDE}" stroke-width="1" '
                    'stroke-dasharray="4 5"/>')
        body.append(f'<line x1="10" x2="590" y1="{_f(bottom)}" y2="{_f(bottom)}" stroke="{GUIDE}" stroke-width="1.2"/>')
        d = stroke_path(name, 40, 580, top, bottom, period)
        body.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="3" stroke-linecap="round" '
                    'stroke-linejoin="round" stroke-dasharray="1 9"/>')
        body.append(f'<circle cx="40" cy="{_f(bottom if name not in ("waves", "loops") else (top + bottom) / 2)}" '
                    f'r="7" fill="{c.get("accent", INK)}"/>')
    return body, len(rows[:6]) * gap


def pattern(b, c: dict, font: str) -> str:
    detail = b.detail
    _, width = DETAIL[detail]
    if b.kind == "trace":
        body, h = trace(list(b.strokes) or ["waves"], detail, c)
        return (f'<svg class="dg dg-pattern" viewBox="0 0 {SIZE} {_f(h)}" width="{SIZE}px" height="{_f(h)}px" '
                f'xmlns="http://www.w3.org/2000/svg">{"".join(body)}</svg>')
    motifs = list(b.motifs) or ["petal"]
    body = mandala(motifs, b.symmetry, detail) if b.kind == "mandala" else tiles(motifs, detail)
    return (f'<svg class="dg dg-pattern" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}px" height="{SIZE}px" '
            f'xmlns="http://www.w3.org/2000/svg"><g fill="#ffffff" stroke="{INK}" stroke-width="{width}" '
            f'stroke-linejoin="round" stroke-linecap="round">{"".join(body)}</g></svg>')
