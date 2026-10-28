"""Phase 4: print-ready tomes — vector colouring pages, trade trim sizes, a KDP cover wrap and a print preflight."""

import io
import shutil

import pytest
from PIL import Image
from pypdf import PdfReader

from app.illustrator import prepare_image, vectorize
from app.printing import page_geometry, preflight, spine_mm
from app.render import render_cover_wrap, render_html, render_pdf
from tests.test_illustrator import png
from tests.test_render import tome

needs_potrace = pytest.mark.skipif(shutil.which("potrace") is None, reason="potrace not installed")
MM = 72 / 25.4  # PDF points per millimetre


def line_art():
    data, _ = prepare_image(png(lambda d: d.ellipse((60, 60, 340, 340), outline="black", width=10)), "line_art")
    return data


def jpeg(size):
    out = io.BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(out, "JPEG")
    return out.getvalue()


@needs_potrace
def test_colouring_pages_become_vector_outlines():
    svg = vectorize(line_art())

    assert svg.startswith(b"<?xml") and b"<path" in svg
    assert b'width="400px"' in svg  # sized like the panel it came from, not in potrace's points


@needs_potrace
def test_a_vector_picture_prints_without_any_raster_image():
    t = tome({"id": "b1", "type": "image", "kind": "line_art", "subject": "una vaca", "size": "full", "asset_id": "a1"})
    t.images = {"a1": (vectorize(line_art()), "image/svg+xml")}

    pdf, _ = render_pdf(t, paper="A4", include_answer_key=False)

    assert not any(page.images for page in PdfReader(io.BytesIO(pdf)).pages)


def test_trade_sizes_set_the_page_and_scale_the_pictures():
    small, big = page_geometry("6x9", print_edition=True), page_geometry("A4", print_edition=False)

    assert (small.w, small.h) == (152.4, 228.6) and small.inner > small.outer  # room for the binding
    assert small.full < big.full and small.content_w < big.content_w


def test_the_print_edition_has_a_title_page_instead_of_the_cover():
    from tests.test_covers import PNG

    t = tome({"id": "b1", "type": "paragraph", "text": "Hola"})
    t.cover_image = PNG

    html = render_html(t, paper="8x10", include_answer_key=False, print_edition=True)
    pdf, _ = render_pdf(t, paper="8x10", include_answer_key=False, print_edition=True)

    assert "Este libro pertenece a" in html and "<img class=\"cover-art\"" not in html
    box = PdfReader(io.BytesIO(pdf)).pages[0].mediabox
    assert (round(float(box.width)), round(float(box.height))) == (576, 720)  # 8 x 10 in


def test_spine_width_follows_the_page_count_and_paper():
    assert spine_mm(100, color=False) == pytest.approx(5.72, abs=0.01)
    assert spine_mm(100, color=True) > spine_mm(100, color=False)


def test_cover_wrap_is_back_spine_and_front_with_bleed():
    from tests.test_covers import PNG

    t = tome({"id": "b1", "type": "paragraph", "text": "Hola"})
    t.cover_image = PNG

    thin, _ = render_cover_wrap(t, paper="8x10", pages=40)
    thick, html = render_cover_wrap(t, paper="8x10", pages=120)

    pages = PdfReader(io.BytesIO(thick)).pages
    width = 2 * 203.2 + spine_mm(120, color=False) + 2 * 3.175
    assert len(pages) == 1 and float(pages[0].mediabox.width) == pytest.approx(width * MM, abs=1)
    assert float(pages[0].mediabox.height) == pytest.approx((254 + 2 * 3.175) * MM, abs=1)
    assert 'class="spine-t"' in html  # KDP allows spine text from 79 pages
    assert 'class="spine-t"' not in render_cover_wrap(t, paper="8x10", pages=40)[1]
    assert "El Do central" in html  # the back cover lists what is inside
    assert thin.startswith(b"%PDF")


def test_preflight_flags_soft_pictures_and_short_books():
    t = tome({"id": "b1", "type": "image", "kind": "illustration", "subject": "un granero", "size": "full",
              "asset_id": "low"},
             {"id": "b2", "type": "image", "kind": "illustration", "subject": "un río", "size": "small",
              "asset_id": "sharp"})
    t.images = {"low": (jpeg((600, 800)), "image/jpeg"), "sharp": (jpeg((1500, 2000)), "image/jpeg")}

    report = preflight(t, paper="Letter", print_edition=True, pages=12)

    assert report["rating"] == "baja" and report["min_dpi"] < 200
    assert any("un granero" in i for i in report["issues"]) and not any("un río" in i for i in report["issues"])
    assert any("24 páginas" in i for i in report["issues"])


@needs_potrace
def test_preflight_passes_vector_art_and_a_sharp_cover():
    t = tome({"id": "b1", "type": "image", "kind": "line_art", "subject": "una vaca", "size": "full", "asset_id": "a1"})
    t.images = {"a1": (vectorize(line_art()), "image/svg+xml")}
    t.cover_image, t.cover_media_type = jpeg((3072, 4096)), "image/jpeg"

    report = preflight(t, paper="Letter", print_edition=False, pages=30)

    assert report == {"rating": "lista", "min_dpi": report["min_dpi"], "issues": [], "vector": 1}
    assert report["min_dpi"] >= 300
