"""Decodable text for literacy tomes (code, no AI): what a child reads uses only the letters taught so far.

The Architect gives each section the letters it teaches (`OutlineSection.letters`) and the tome the letters
known before it starts (`Outline.known_letters`); a section may use those plus everything taught before it.
Pictured words are hints read by the teacher, so they only have to contain the syllable they illustrate.
check_blocks and tidy catch block misuse in any tome (counting with syllable blocks, blank pages).
"""

import re
import unicodedata

from app.content import Outline, SectionContent

DIGRAPHS = ("ch", "ll", "rr", "qu")
PLAIN = str.maketrans("áéíóúü", "aeiouu")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lower()).translate(PLAIN)
    return re.sub(r"[^a-zñ ]", " ", text)


def graphemes(word: str) -> list[str]:
    word, out, i = _fold(word).replace(" ", ""), [], 0
    while i < len(word):
        pair = word[i:i + 2]
        if pair in DIGRAPHS:
            out.append(pair)
            i += 2
        else:
            out.append(word[i])
            i += 1
    return out


def allowed_letters(outline: Outline, position: int) -> set[str] | None:
    """None when the tome is not a literacy method (no section teaches letters)."""
    if not any(s.letters for s in outline.sections):
        return None
    allowed = {_fold(x).strip() for x in outline.known_letters}
    for s in outline.sections[:position]:
        allowed |= {_fold(x).strip() for x in s.letters}
    return allowed


def _unknown(text: str, allowed: set[str]) -> list[str]:
    def ok(g: str) -> bool:
        return g in allowed or (g == "rr" and "r" in allowed)  # rr is taught with the r

    return sorted({g for w in _fold(text).split() for g in graphemes(w) if not ok(g)})


def _has(word: str, syllable: str) -> bool:
    return _fold(syllable).strip() in _fold(word).replace(" ", "")


def check_section(content: SectionContent, allowed: set[str] | None) -> list[str]:
    """Problems in Spanish, one per offending word, phrased so the Writer can fix them."""
    if allowed is None:
        return []
    problems: list[str] = []

    def readable(block_id: str, text: str):
        for word in text.split():
            bad = _unknown(word, allowed)
            if bad:
                clean = word.strip(".,;:¡!¿?«»\"'()")
                problems.append(f"«{clean}» ({block_id}) usa letras aún no vistas: {', '.join(bad)}")

    for b in content.blocks:
        if b.type == "reading":
            for line in b.sentences:
                readable(b.id, line.text)
        elif b.type == "dictation":
            for w in b.words:
                readable(b.id, w)
        elif b.type == "fill_sentences":
            for item in b.items:
                readable(b.id, item.text.replace("___", " "))
                readable(b.id, item.answer)
        elif b.type in ("word_search", "classify"):
            for w in b.words:
                readable(b.id, w)
        elif b.type == "syllable_cards":
            for s in b.syllables:
                readable(b.id, s)
        if b.type == "syllable_chart":
            for w in b.words:
                if not _has(w.word, w.syllable):
                    problems.append(f"«{w.word}» ({b.id}) no contiene la sílaba «{w.syllable}»")
        elif b.type == "picture_words" and b.mode != "write":
            for item in b.items:
                if not _has(item.word, item.syllable):
                    problems.append(f"«{item.word}» ({b.id}) no contiene la sílaba «{item.syllable}»")
        elif b.type == "classify":
            for w in b.words:
                fits = [c for c in b.columns if _has(w, c)]
                if len(fits) != 1:
                    where = "ninguna columna" if not fits else f"varias columnas ({', '.join(fits)})"
                    problems.append(f"«{w}» ({b.id}) encaja en {where}")
    return problems


QUANTITY = re.compile(r"[+−×÷=]|\b\d{1,2}\s+[a-záéíóúñ]", re.I)  # "2 manzanas", "3 + 1"


def check_blocks(content: SectionContent) -> list[str]:
    """Blocks used for what another block does exactly: counts and sums belong to code-drawn blocks."""
    problems: list[str] = []
    for b in content.blocks:
        if b.type == "picture_words" and any(re.search(r"\d", i.syllable or "") for i in b.items):
            problems.append(f"{b.id}: picture_words es para sílabas; para contar dibujos usa counting")
        elif b.type == "image" and b.kind in ("line_art", "illustration") and QUANTITY.search(b.subject):
            problems.append(f"{b.id}: una image no muestra cantidades ni operaciones («{b.subject}»); usa counting "
                            "o picture_math")
    return problems


def tidy(content: SectionContent, section_title: str) -> None:
    """Drop what prints badly: a first heading that repeats the section opener, and page breaks that would
    leave a blank page (doubled or at the end)."""
    blocks = content.blocks
    if blocks and blocks[0].type == "heading" and blocks[0].text.strip().lower() == section_title.strip().lower():
        blocks = blocks[1:]
    blocks = [b for i, b in enumerate(blocks) if b.type != "page_break" or (i + 1 < len(blocks)
              and blocks[i + 1].type != "page_break")]
    content.blocks = blocks or content.blocks
