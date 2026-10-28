"""The cost shown before creating a tome."""

from app.pricing import COVER_USD, estimate


def test_more_pages_cost_more_and_art_is_a_range():
    small, big = estimate(1, 3), estimate(10, 60)

    assert small["pages"] == 3 and big["total_usd"][0] > small["total_usd"][0]
    assert small["total_usd"][0] >= COVER_USD and small["total_usd"][1] > small["total_usd"][0]
    assert big["text_usd"] < 0.1  # DeepSeek text stays cents even for a long tome


def test_unset_choices_are_assumed_and_flagged():
    auto = estimate(None, None)

    assert auto["assumed"] == {"sections": True, "pages": True} and auto["pages"] == auto["sections"] * 3 + 1
    assert estimate(None, 24)["sections"] == 8 and estimate(5, None)["pages"] == 16


def test_past_tomes_give_a_real_figure():
    assert estimate(3, 10, history_per_page=0.02)["history_usd"] == 0.2
