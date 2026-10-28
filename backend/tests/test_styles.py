"""Phase 9: the style library — reference pages in, a printable theme out (style only, never the artwork)."""

import io

from PIL import Image
from weasyprint import HTML

from app.content import Design
from app.render import render_html
from app.styles import contact_sheet, contrast, print_palette, read_spec, sample_pages, theme_from_spec
from tests.test_render import tome


def reference_pdf(pages=12) -> bytes:
    html = "".join(f'<p style="break-after: page; font-size: 40pt; color: #E8762C">Ficha {i}</p>' for i in range(pages))
    return HTML(string=f"<style>@page {{ size: 216mm 279mm }}</style>{html}").write_pdf()


def test_a_reference_pdf_is_sampled_into_at_most_eight_pages():
    pages = sample_pages(reference_pdf(), "application/pdf")

    assert len(pages) == 8 and all(p.startswith(b"\xff\xd8") for p in pages)
    assert max(Image.open(io.BytesIO(pages[0])).size) == 900


def test_an_image_reference_is_one_page():
    out = io.BytesIO()
    Image.new("RGB", (2000, 1500), "pink").save(out, "PNG")

    assert len(sample_pages(out.getvalue(), "image/png")) == 1


def test_the_contact_sheet_numbers_every_page_on_one_image():
    sheet = Image.open(io.BytesIO(contact_sheet(sample_pages(reference_pdf(6), "application/pdf"))))

    assert sheet.size == (4 * 460, 2 * 600)


def test_a_dark_or_washed_out_palette_is_fixed_for_print():
    bg, ink, accent = print_palette(["#203040", "#8899AA", "#FAFAF0"])

    assert contrast(ink, "#FFFFFF") >= 7 and contrast(accent, bg) >= 2.2 and contrast(bg, "#000000") > 15


def test_an_imperfect_reading_keeps_what_is_valid():
    spec = read_spec({"best_pages": [2, 9, "x"], "score": 8, "palette": ["#FFF8EC", "#2D2A5A", "naranja"],
                      "heading_look": "script", "frame": "zigzag", "traits": ["Pestaña Ficha N"]}, pages=8)

    assert spec.best_pages == [2] and spec.score == 8 and spec.heading_look == "script"
    assert spec.frame == "none" and spec.traits == ["Pestaña Ficha N"] and len(spec.palette) == 3


def test_the_theme_maker_builds_a_printable_design_with_font_frame_and_art_style():
    spec = read_spec({"palette": ["#FFFFFF", "#111111", "#E8762C"], "heading_look": "script", "frame": "rounded",
                      "ornament": "estrellas", "color_use": "bw",
                      "illustration_style": "thick black outline clip-art"}, pages=4)

    design = theme_from_spec(spec, name="Método 20 días", style_id="s1")

    assert design.theme == "cuaderno" and design.head_font == "Pacifico" and design.frame == "rounded"
    assert "thick black outline" in design.art_style and "black and white" in design.art_style
    assert design.style_id == "s1" and "Método 20 días" in design.rationale


def test_a_library_style_prints_its_font_and_page_frame():
    t = tome({"id": "h", "type": "heading", "level": 2, "text": "Ficha 1"},
             {"id": "p", "type": "paragraph", "text": "Hola"})
    t.design = Design(theme="cuaderno", palette=["#FFF8EC", "#2D2A5A", "#E8762C"], head_font="Pacifico",
                      frame="dashed")

    html = render_html(t, paper="Letter", include_answer_key=False)

    assert "Pacifico-Regular.ttf" in html and "dashed #2D2A5A" in html and 'class="b tab"' in html
