"""The free library's copyright: one line set vertically along the outer edge of every page of a published book,
so a copy passed around still says whose it is and that it is not for sale. WeasyPrint sets the line on a blank
page of the same size and pdfium lays that page over each one as a form, so the book's own pages stay untouched."""

import html
import io

import pypdfium2
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
    """The book with `line` along the right edge of each page."""
    book = pypdfium2.PdfDocument(pdf)
    overlays: dict[tuple[int, int], tuple] = {}
    for i in range(len(book)):
        page = book[i]
        w, h = page.get_size()
        key = (round(w), round(h))
        if key not in overlays:
            source = pypdfium2.PdfDocument(_overlay(w, h, line))
            overlays[key] = (source, source.page_as_xobject(0, book))
        _, xobject = overlays[key]
        page.insert_obj(xobject.as_pageobject())
        page.gen_content()
    out = io.BytesIO()
    book.save(out)
    for source, _ in overlays.values():
        source.close()
    return out.getvalue()


def library_line(title: str, year: int, brand: str = "Jelyx Docs") -> str:
    return (f"© {year} {brand} · «{title}» · Descarga gratuita para uso personal y en el aula · "
            f"Prohibida su venta o redistribución")
