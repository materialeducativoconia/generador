"""Phase 8: literacy worksheets only use letters the child already knows (checked by code, not by the model)."""

from app.content import Outline, SectionContent
from app.literacy import allowed_letters, check_blocks, check_section, graphemes, tidy

OUTLINE = Outline(title="Método", genre="worksheets", known_letters=["a", "e", "i", "o", "u"], sections=[
    {"title": "La m", "letters": ["m"]}, {"title": "La p", "letters": ["p"]}, {"title": "La ch", "letters": ["ch"]}])


def section(*blocks):
    return SectionContent.model_validate({"schema_version": 1, "blocks": list(blocks)})


def test_graphemes_handle_accents_and_digraphs():
    assert graphemes("Mamá") == ["m", "a", "m", "a"]
    assert graphemes("chupón") == ["ch", "u", "p", "o", "n"]
    assert graphemes("queso") == ["qu", "e", "s", "o"] and graphemes("niño") == ["n", "i", "ñ", "o"]


def test_each_section_may_use_what_was_taught_so_far():
    assert allowed_letters(OUTLINE, 1) == {"a", "e", "i", "o", "u", "m"}
    assert allowed_letters(OUTLINE, 3) == {"a", "e", "i", "o", "u", "m", "p", "ch"}
    assert allowed_letters(Outline(title="x", genre="tutorial", sections=[{"title": "s"}]), 1) is None


def test_sentences_with_unknown_letters_are_reported():
    content = section(
        {"id": "r", "type": "reading", "sentences": [{"text": "Mi mamá me ama."}, {"text": "Mi papá come pan."}]},
        {"id": "d", "type": "dictation", "words": ["mapa", "sopa"]})

    problems = check_section(content, allowed_letters(OUTLINE, 2))

    assert any("come" in p and "c" in p for p in problems) and any("sopa" in p and "s" in p for p in problems)
    assert not any("mamá" in p for p in problems)


def test_pictured_words_only_need_their_syllable():
    """A template may show «mesa» before the s is taught; it must contain the syllable it illustrates."""
    content = section(
        {"id": "c", "type": "syllable_chart", "letter": "m", "words": [
            {"word": "mesa", "syllable": "me"}, {"word": "moto", "syllable": "mo"},
            {"word": "mano", "syllable": "ma"}, {"word": "pato", "syllable": "mu"}]},
        {"id": "w", "type": "picture_words", "mode": "complete", "items": [
            {"word": "mono", "syllable": "mo"}, {"word": "luna", "syllable": "mi"}]})

    problems = check_section(content, allowed_letters(OUTLINE, 1))

    assert len(problems) == 2 and any("pato" in p for p in problems) and any("luna" in p for p in problems)


def test_classify_words_must_fit_exactly_one_column():
    content = section({"id": "k", "type": "classify", "columns": ["ma", "pa"],
                       "words": ["mapa", "mamá", "papá", "mimo"]})

    problems = check_section(content, allowed_letters(OUTLINE, 2))

    assert any("mapa" in p for p in problems) and any("mimo" in p for p in problems) and len(problems) == 2


def test_a_tome_without_letters_is_not_checked():
    content = section({"id": "r", "type": "reading", "sentences": [{"text": "Cualquier cosa vale."}]})

    assert check_section(content, None) == []


def test_counting_with_syllable_or_picture_blocks_is_sent_back():
    content = section(
        {"id": "b1", "type": "picture_words", "mode": "circle", "items": [{"word": "sol", "syllable": "3"},
                                                                          {"word": "luna", "syllable": "1"}]},
        {"id": "b2", "type": "image", "kind": "line_art", "subject": "2 manzanas + 1 manzana", "size": "half"},
        {"id": "b3", "type": "image", "kind": "photo", "subject": "Apolo 11 en la Luna", "size": "half"},
        {"id": "b4", "type": "image", "kind": "line_art", "subject": "una ardilla feliz", "size": "half"})

    problems = check_blocks(content)

    assert [p.split(":")[0] for p in problems] == ["b1", "b2"]


def test_tidy_drops_a_repeated_title_and_blank_pages():
    content = section({"id": "b1", "type": "heading", "level": 2, "text": "Sumas hasta 5"},
                      {"id": "b2", "type": "paragraph", "text": "Hola"}, {"id": "b3", "type": "page_break"},
                      {"id": "b4", "type": "page_break"}, {"id": "b5", "type": "paragraph", "text": "Fin"},
                      {"id": "b6", "type": "page_break"})

    tidy(content, "Sumas hasta 5")

    assert [b.id for b in content.blocks] == ["b2", "b4", "b5"]
