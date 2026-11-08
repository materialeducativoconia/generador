import io
import random

from PIL import Image

from app.content import Image as Plate
from app.textlook import CARD, LIGHT, OPEN, patch_look, plate_looks

INK = "#1c1917"
PAGE = (170.0, 210.0)
TOP = (0.05, 0.04, 0.95, 0.24)


def picture(fill, noisy_top=False) -> bytes:
    im = Image.new("RGB", (600, 800), fill)
    if noisy_top:  # foliage: leaves of every tone
        rnd = random.Random(1)
        for x in range(0, 600, 6):
            for y in range(0, 200, 6):
                v = rnd.randrange(30, 230)
                im.paste((v, v + 20 if v < 235 else v, v), (x, y, x + 6, y + 6))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def test_a_pale_plain_sky_takes_the_ink_straight_on_the_picture():
    assert patch_look(picture((214, 234, 248)), TOP, PAGE, INK) == OPEN


def test_a_dark_plain_night_takes_white_words():
    assert patch_look(picture((24, 32, 64)), TOP, PAGE, INK) == LIGHT


def test_foliage_or_a_mid_tone_keeps_the_card():
    assert patch_look(picture((214, 234, 248), noisy_top=True), TOP, PAGE, INK) == CARD
    assert patch_look(picture((128, 128, 128)), TOP, PAGE, INK) == CARD  # neither ink reads at 4.5:1


def test_every_text_of_a_plate_is_judged_where_it_prints():
    plate = Plate.model_validate({"id": "p1", "type": "image", "kind": "illustration", "size": "plate", "subject": "x",
                                  "question": "¿Qué ves?", "answer": "Un cielo.", "find": "¿Dónde está el sol?",
                                  "notes": ["Hace sol."]})
    looks = plate_looks(plate, picture((214, 234, 248), noisy_top=True), PAGE, INK, False,
                        {"n0": (0.03, 0.5, 0.34, 0.6)})

    assert looks == {"q": CARD, "f": OPEN, "n0": OPEN}  # the busy top keeps its card, the plain rest does not
    assert plate_looks(plate, None, PAGE, INK, False, {}) == {}  # no picture yet: cards
