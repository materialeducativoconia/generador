"""What a tome will cost in AI calls, estimated before it is created (USD for now; credits later).

Measured prices: one image call costs about $0.038 at 1K, $0.057 at 2K and ~$0.09 at 4K (OpenRouter); a 4K
cover is one call. DeepSeek text is priced from app.llm.USD_PER_M with typical token counts of our agents.
Illustrations depend on what the Architect plans (none, worksheet pictures, colour art), so they are a range.
"""

from app.llm import USD_PER_M

PLANNING_TOKENS = {"miss": 9000, "hit": 3000, "out": 3500}  # researcher, architect, designer, cover, art director
SECTION_TOKENS = {"miss": 4000, "hit": 6000, "out": 900}  # writer + editor around one section
PAGE_TOKENS = {"miss": 300, "hit": 0, "out": 1100}  # each printed page the Writer fills
COVER_USD = 0.09
SEARCH_USD = 0.02  # program searcher: up to three Perplexity Sonar searches with their citations
# Illustration per page: worksheet pictures reused from the library (low) up to a 4K colour picture shared
# four to a sheet, plus the vision review (high).
ART_PER_PAGE_USD = (0.0, 0.024)
DEFAULT_SECTIONS, PAGES_PER_SECTION = 8, 3


def _usd(tokens: dict, times: float = 1) -> float:
    return sum(tokens[k] * USD_PER_M[k] for k in tokens) / 1e6 * times


def estimate(sections: int | None, pages: int | None, history_per_page: float | None = None) -> dict:
    """`history_per_page` is what this user's finished tomes really cost per page, when there are any."""
    n = sections or (max(1, round(pages / PAGES_PER_SECTION)) if pages else DEFAULT_SECTIONS)
    p = pages or n * PAGES_PER_SECTION + 1
    text = _usd(PLANNING_TOKENS) + _usd(SECTION_TOKENS, n) + _usd(PAGE_TOKENS, p)
    low, high = (text + SEARCH_USD + COVER_USD + p * a for a in ART_PER_PAGE_USD)
    out = {"sections": n, "pages": p, "assumed": {"sections": sections is None, "pages": pages is None},
           "text_usd": round(text, 3), "search_usd": SEARCH_USD, "cover_usd": COVER_USD,
           "art_usd": [round(p * a, 3) for a in ART_PER_PAGE_USD],
           "total_usd": [round(low, 2), round(high, 2)], "currency": "USD"}
    if history_per_page:
        out["history_usd"] = round(history_per_page * p, 2)
    return out
