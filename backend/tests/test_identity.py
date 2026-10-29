"""The Brand guard and the imprint: code keeps identities printable, distinct, and on every page."""

from app.content import Brand, Design, Mascot
from app.identity import guard, initials, look_key, mark_svg
from app.render import Tome, render_html
from tests.test_render import tome

LOOK = {"theme": "juego", "palette": ["#2B2A4C", "#777777", "#FFF5F5"], "illustration": "acuarela",
        "cover_layout": "plate", "head_font": "Fredoka"}


def test_initials_skip_filler_words():
    assert initials("Ediciones La Semillita") == "S"
    assert initials("Taller Brújula") == "TB"


def test_the_guard_makes_three_lookalikes_distinct_and_printable():
    looks = [Design.model_validate(LOOK) for _ in range(3)]
    taken = {look_key(looks[0])}  # one of the user's identities already looks like this

    out = guard(looks, taken)

    keys = [look_key(d) for d in out]
    assert len(set(keys)) == 3 and not taken & set(keys)
    assert all(d.art_style for d in out)
    assert out[0].palette[0] != "#2B2A4C"  # a dark page background is lightened for print


def test_the_seal_escapes_its_letters():
    svg = mark_svg(Brand(name="Lápiz & Co", initials="<&>", mark="shield"), "#C8553D")
    assert "<&>" not in svg and "&lt;&amp;&gt;" in svg and 'fill="#C8553D"' in svg


def test_a_tome_of_a_line_prints_its_imprint_and_level():
    brand = Brand(name="Semillita", tagline="Aprender jugando", voice="Tú, cercana",
                  mascot=Mascot(name="Luna", look="a small owl"), mark="leaf")
    t: Tome = tome({"id": "p1", "type": "paragraph", "text": "Hola"})
    t.design = Design(theme="juego", palette=["#FFFDF7", "#1C1917", "#2F855A"], brand=brand)
    t.collection, t.level = "Multiplicación", 2

    html = render_html(t, paper="A4", include_answer_key=False)

    assert "Multiplicación · Nivel 2" in html
    assert 'class="imprint"' in html and 'content: "Semillita"' in html and 'class="seal"' in html
