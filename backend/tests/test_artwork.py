import io
import json

import httpx
from PIL import Image, ImageDraw

from app.agents import Brief, art_director
from app.artwork import ImageRequest, plan_sheets, sheet_prompt, slice_sheet
from app.content import ArtPlan, Design
from app.vision import OpenRouterVision
from tests.fakes import ScriptedLLM

DESIGN = Design(theme="juego", palette=["#FFF8EC", "#2D2A5A", "#E8762C"], ornament="notas")


def req(ref, kind="line_art", size="full", subject="un ratón"):
    return ImageRequest(ref=ref, lesson_id="L", block_id=ref, kind=kind, size=size, subject=subject)


def grid(cols, rows, panel=(300, 400), gutter_at=0.5):
    """A fake sheet: one outlined ellipse per cell, white gutters between cells."""
    w, h = panel[0] * cols, panel[1] * rows
    xs = [0, int(w * gutter_at), w] if cols == 2 else [0, w]
    ys = [0, int(h * gutter_at), h] if rows == 2 else [0, h]
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    for c in range(cols):
        for r in range(rows):
            d.ellipse((xs[c] + 40, ys[r] + 40, xs[c + 1] - 40, ys[r + 1] - 40), outline="black", width=6)
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def test_requests_are_grouped_by_family_and_size_into_sheets_of_four():
    reqs = [req(f"a{i}") for i in range(5)] + [req("c1", kind="illustration"), req("h1", size="half")]

    sheets = plan_sheets(reqs)

    shapes = sorted((s.family, s.aspect, len(s.requests), s.cols, s.rows) for s in sheets)
    assert shapes == [("colour", "3:4", 1, 1, 1), ("line", "3:4", 1, 1, 1), ("line", "3:4", 4, 2, 2),
                      ("line", "4:3", 1, 1, 1)]


def test_two_or_three_requests_still_share_one_sheet():
    sheets = plan_sheets([req("a"), req("b"), req("c")])

    assert len(sheets) == 1 and (sheets[0].cols, sheets[0].rows) == (2, 2)


def test_sheet_prompt_names_every_panel_and_the_style_bible():
    plan = ArtPlan(style="Soft rounded flat vector, thick lines", characters=[
        {"name": "Rito", "look": "a plush mouse with an orange scarf"}], prompts={"a": "Rito waves", "b": "Rito sits"})
    sheet = plan_sheets([req("a"), req("b")])[0]

    prompt = sheet_prompt(sheet, plan, DESIGN)

    assert "2x2 grid" in prompt and "top-left: Rito waves" in prompt and "top-right: Rito sits" in prompt
    assert "empty" in prompt.lower()  # unused slots stay blank
    assert "orange scarf" in prompt and "Soft rounded flat vector" in prompt and "no text" in prompt.lower()


def test_a_2x2_sheet_is_cut_into_four_trimmed_panels():
    panels = slice_sheet(grid(2, 2), 2, 2)

    assert len(panels) == 4
    for data in panels:
        im = Image.open(io.BytesIO(data)).convert("L")
        assert min(im.get_flattened_data()) == 0  # each panel kept its drawing
        assert im.width < 300 and im.height < 400  # trimmed to content plus a margin


def test_slicing_follows_gutters_that_are_not_exactly_centred():
    panels = slice_sheet(grid(2, 2, gutter_at=0.44), 2, 2)

    assert len(panels) == 4 and all(Image.open(io.BytesIO(p)).width > 60 for p in panels)


def test_a_single_image_sheet_is_returned_whole():
    assert len(slice_sheet(grid(1, 1), 1, 1)) == 1


async def test_art_director_writes_one_style_for_the_whole_tome():
    reply = {"style": "Soft rounded flat vector", "characters": [{"name": "Rito", "look": "plush mouse"}],
             "prompts": {"1:b2": "Rito at the piano", "9:zz": "ignored"}}
    llm = ScriptedLLM(json.dumps(reply))
    requests = [req("1:b2", subject="un ratón al piano"), req("1:b5", subject="una mano con caritas")]

    result = await art_director(llm, Brief(request="piano", audience="Preescolar"), "Mi primer piano", DESIGN,
                                "Un ratón pianista", requests)

    assert result.value.prompts == {"1:b2": "Rito at the piano", "1:b5": "una mano con caritas"}
    user = llm.calls[0][1]["content"]
    assert "1:b2" in user and "una mano con caritas" in user and "Un ratón pianista" in user


async def test_sheet_review_returns_one_verdict_per_panel():
    verdicts = {"panels": [{"ok": True}, {"ok": False, "has_text": True, "issues": "letras"}]}
    vision = OpenRouterVision("k", "m", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(verdicts)}}]})))

    reviews = await vision.review_sheet(grid(2, 1), ["un ratón", "una mano"], kind="line_art")

    assert [r.ok for r in reviews] == [True, False] and reviews[1].has_text
