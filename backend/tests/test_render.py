import io

from pypdf import PdfReader

from app.content import SectionContent
from app.render import Tome, TomeSection, render_html, render_pdf, inline


def tome(*blocks, genre="tutorial"):
    content = SectionContent.model_validate({"schema_version": 1, "summary": "", "blocks": list(blocks)})
    return Tome(title="Piano desde cero", genre=genre, audience="Adultos", author="Marta Pérez",
                sections=[TomeSection(position=1, title="El Do central", content=content)])


def test_inline_formatting_escapes_html_before_bold_and_italic():
    assert inline("<script>x</script> **Do** y *Re*") == (
        "&lt;script&gt;x&lt;/script&gt; <strong>Do</strong> y <em>Re</em>"
    )


def test_keyboard_highlights_the_requested_keys():
    html = render_html(tome({"id": "b1", "type": "keyboard", "start": "C4", "octaves": 1,
                             "highlight": ["C4", "E4"]}), paper="A4", include_answer_key=False)

    assert html.count('class="white on"') == 2
    assert html.count('class="white"') == 5
    assert html.count('class="black"') == 5


def test_answers_go_to_the_answer_key_only():
    t = tome({"id": "b1", "type": "exercise", "kind": "open", "prompt": "¿Qué nota es?", "answer": "Es un Do"})

    with_key = render_html(t, paper="A4", include_answer_key=True)
    without_key = render_html(t, paper="A4", include_answer_key=False)

    assert with_key.count("Es un Do") == 1 and 'id="solucionario"' in with_key
    assert "Es un Do" not in without_key


def test_letter_grid_is_deterministic_and_contains_every_target():
    block = {"id": "b1", "type": "letter_grid", "targets": ["A"], "distractors": ["m", "o"], "rows": 3, "cols": 3}

    first = render_html(tome(block), paper="A4", include_answer_key=False)
    second = render_html(tome(block), paper="A4", include_answer_key=False)

    assert first == second
    assert ">A<" in first


def test_pdf_renders_with_embedded_fonts():
    pdf, pages = render_pdf(tome(
        {"id": "b1", "type": "heading", "level": 2, "text": "Repasa"},
        {"id": "b2", "type": "tracing", "text": "Aa", "repeat": 3},
        {"id": "b3", "type": "image", "kind": "line_art", "subject": "una ardilla"},
    ), paper="Letter", include_answer_key=True)

    assert pdf.startswith(b"%PDF")
    assert pages >= 2  # cover + section (contents only appears with 2+ sections)
    fonts = {font["/BaseFont"] for page in PdfReader(io.BytesIO(pdf)).pages
             for font in page["/Resources"].get("/Font", {}).values()}
    assert any("Andika" in f for f in fonts) and any("Nunito" in f for f in fonts)
