"""The Layout designer: plates get varied compositions before they are painted."""

from app.artwork import ImageRequest, plan_sheets
from app.content import SectionContent
from app.layout import lay_out


def plates(n, **extra):
    return SectionContent.model_validate({"blocks": [
        {"id": f"p{i}", "type": "image", "kind": "illustration", "size": "plate", "subject": "un ave", **extra}
        for i in range(n)]})


def test_plates_never_repeat_the_previous_composition_and_a_spare_page_becomes_a_spread():
    content = plates(4)
    lay_out(content, position=1, pages=5, house_style=None)
    layouts = [b.layout for b in content.blocks]
    assert layouts.count("spread") == 1 and layouts[1] == "spread"
    assert all(a != b for a, b in zip(layouts, layouts[1:]))


def test_no_spare_page_no_spread_and_the_house_style_sets_the_taste():
    content = plates(3)
    lay_out(content, position=1, pages=3, house_style="enciclopedia")
    assert [b.layout for b in content.blocks] == ["vignette", "bleed", "band"]


def test_a_plate_with_a_diagram_keeps_the_full_bleed():
    content = plates(1, inset={"id": "i", "type": "sizes", "items": [{"label": "a", "size": 1}, {"label": "b", "size": 2}]})
    lay_out(content, position=1, pages=4, house_style=None)
    assert content.blocks[0].layout == "bleed"


def test_each_composition_is_painted_in_its_own_aspect():
    reqs = [ImageRequest(ref=str(i), lesson_id="l", block_id=str(i), kind="illustration", size="plate", subject="x",
                         layout=lay) for i, lay in enumerate(["spread", "band", "vignette", None])]
    assert sorted(s.aspect for s in plan_sheets(reqs)) == ["1:1", "3:2", "3:4", "4:3"]
