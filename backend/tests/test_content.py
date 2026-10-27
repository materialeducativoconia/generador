import pytest
from pydantic import ValidationError

from app.content import Outline, SectionContent


def section(*blocks):
    return {"schema_version": 1, "summary": "Resumen", "blocks": list(blocks)}


def test_section_accepts_every_page_block_type():
    content = SectionContent.model_validate(
        section(
            {"id": "b1", "type": "heading", "level": 2, "text": "Do central"},
            {"id": "b2", "type": "paragraph", "text": "Pon el **pulgar** en el Do."},
            {"id": "b3", "type": "list", "style": "number", "items": ["Siéntate", "Relaja"]},
            {"id": "b4", "type": "callout", "variant": "tip", "title": "Consejo", "text": "Despacio."},
            {"id": "b5", "type": "table", "headers": ["Nota", "Dedo"], "rows": [["Do", "1"]]},
            {"id": "b6", "type": "keyboard", "start": "C4", "octaves": 1, "highlight": ["C4", "E4", "G4"]},
            {"id": "b7", "type": "tracing", "text": "Aa", "repeat": 4},
            {"id": "b8", "type": "letter_grid", "targets": ["A", "a"], "distractors": ["m", "o"]},
            {"id": "b9", "type": "image", "kind": "line_art", "subject": "una ardilla con una bellota"},
            {"id": "b10", "type": "writing_lines", "lines": 4},
            {"id": "b11", "type": "exercise", "kind": "multiple_choice", "prompt": "¿Qué nota?",
             "options": ["Do", "Re"], "answer": "Do"},
            {"id": "b12", "type": "activity", "title": "Practica", "steps": ["Toca Do-Re-Mi"]},
            {"id": "b13", "type": "page_break"},
        )
    )

    assert [b.type for b in content.blocks][:3] == ["heading", "paragraph", "list"]


def test_unknown_block_type_is_rejected():
    with pytest.raises(ValidationError):
        SectionContent.model_validate(section({"id": "b1", "type": "video", "url": "x"}))


def test_duplicate_block_ids_are_rejected():
    with pytest.raises(ValidationError, match="únicos"):
        SectionContent.model_validate(
            section({"id": "b1", "type": "paragraph", "text": "a"}, {"id": "b1", "type": "paragraph", "text": "b"})
        )


def test_keyboard_rejects_notes_that_are_not_scientific_pitch():
    with pytest.raises(ValidationError):
        SectionContent.model_validate(section({"id": "b1", "type": "keyboard", "start": "C4", "highlight": ["Do"]}))


def test_empty_section_is_rejected():
    with pytest.raises(ValidationError):
        SectionContent.model_validate(section())


def test_outline_needs_between_one_and_twenty_sections():
    sec = {"title": "Colorea la granja", "objectives": ["Motricidad fina"], "key_points": ["vaca"]}
    ok = Outline.model_validate({"title": "Granja", "genre": "coloring_book", "sections": [sec]})
    assert ok.genre == "coloring_book"

    with pytest.raises(ValidationError):
        Outline.model_validate({"title": "Granja", "genre": "coloring_book", "sections": [sec] * 21})


def test_outline_unknown_genre_is_rejected():
    with pytest.raises(ValidationError):
        Outline.model_validate({"title": "X", "genre": "novela", "sections": [{"title": "a"}]})
