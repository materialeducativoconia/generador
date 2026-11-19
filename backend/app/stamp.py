"""The free library's copyright: one line set vertically along the outer edge of every page of a published book,
so a copy passed around still says whose it is and that it is not for sale. WeasyPrint sets the line on a blank
page of the same size and pypdf lays that page over each one, so the book's own pages stay untouched."""

import html
import io

import pypdf
import weasyprint

PT_TO_MM = 25.4 / 72


def _overlay(width_pt: float, height_pt: float, line: str) -> bytes:
    w, h = width_pt * PT_TO_MM, height_pt * PT_TO_MM
    # The line runs bottom to top, 4 mm inside the right edge, on a pale band so it reads over a full-bleed picture.
    doc = f"""<html><head><style>
      @page {{ size: {w:.2f}mm {h:.2f}mm; margin: 0; }}
      html, body {{ margin: 0; background: transparent; }}
      .edge {{ position: absolute; left: {w - 4:.2f}mm; top: {h / 2:.2f}mm; width: {h - 16:.2f}mm;
               transform: translate(-50%, -50%) rotate(-90deg); transform-origin: center;
               margin-left: 0; text-align: center; white-space: nowrap; overflow: hidden;
               font: 600 6.5pt Nunito, sans-serif; letter-spacing: .02em; color: rgba(60, 56, 52, .78); }}
      .edge span {{ background: rgba(255, 255, 255, .72); padding: .5mm 2mm; border-radius: 2mm; }}
    </style></head><body><div class="edge"><span>{html.escape(line)}</span></div></body></html>"""
    return weasyprint.HTML(string=doc).write_pdf()


def copyright_edge(pdf: bytes, line: str) -> bytes:
    """The book with `line` along the right edge of each page. pypdf lays the line's page over each one and keeps
    the book's own content stream as it is: pdfium regenerated it (gen_content) and garbled the cover's outlined title."""
    book = pypdf.PdfWriter(clone_from=pypdf.PdfReader(io.BytesIO(pdf)))
    overlays: dict[tuple[int, int], pypdf.PageObject] = {}
    for page in book.pages:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        key = (round(w), round(h))
        if key not in overlays:
            overlays[key] = pypdf.PdfReader(io.BytesIO(_overlay(w, h, line))).pages[0]
        page.merge_page(overlays[key], over=True)
    out = io.BytesIO()
    book.write(out)
    return out.getvalue()


def library_line(title: str, year: int, brand: str = "Jelyx Docs") -> str:
    return (f"© {year} {brand} · «{title}» · Descarga gratuita para uso personal y en el aula · "
            f"Prohibida su venta o redistribución")
