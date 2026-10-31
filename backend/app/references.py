"""Reference covers of real, published educational books (Open Library), for the cover agent.

They are a mood board for the image model, never reproduced: the prompt forbids copying them.
"""

import asyncio
import re
import unicodedata
from dataclasses import dataclass

import httpx

USER_AGENT = "JelyxDocs/1.0 (+https://jelyx.app)"
# Open Library matches these against every field, so "book cover" pulls in unrelated books.
NOISE = {"cover", "covers", "book", "books", "libro", "libros", "portada", "portadas", "illustration",
         "ilustracion", "flat", "vector", "style", "estilo"}


def _words(value: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", plain)


def _clean(query: str) -> str:
    return " ".join(w for w in _words(query) if w not in NOISE)


def _related(title: str, query: str) -> bool:
    wanted = {w for w in _words(query) if len(w) >= 4}
    return not wanted or bool(wanted & set(_words(title)))


@dataclass
class Reference:
    title: str
    source_url: str
    image_url: str
    data: bytes


async def _search(http: httpx.AsyncClient, query: str) -> list[dict]:
    for attempt in range(2):  # Open Library drops the odd connection
        try:
            response = await http.get("https://openlibrary.org/search.json",
                                      params={"q": query, "fields": "title,cover_i,key", "limit": 20})
            response.raise_for_status()
            return response.json().get("docs", [])
        except httpx.TransportError:
            if attempt:
                return []
            await asyncio.sleep(0.5)
        except (httpx.HTTPError, ValueError):
            return []
    return []


async def find_covers(queries: list[str], *, limit: int = 4, timeout: float = 15,
                      transport: httpx.AsyncBaseTransport | None = None) -> list[Reference]:
    """Best effort: any failure just means fewer references."""
    async with httpx.AsyncClient(timeout=timeout, transport=transport, headers={"User-Agent": USER_AGENT},
                                 follow_redirects=True) as http:
        found: list[tuple[str, str, str]] = []
        for query in filter(None, map(_clean, queries)):
            docs = await _search(http, query)
            for doc in docs:
                if (doc.get("cover_i") and _related(doc.get("title", ""), query)
                        and all(doc["title"] != t for t, _, _ in found)):
                    found.append((doc["title"], f"https://openlibrary.org{doc.get('key', '')}",
                                  f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg?default=false"))
            if len(found) >= limit * 2:
                break

        async def download(item):
            title, source, image = item
            try:
                response = await http.get(image)
                if response.status_code == 200 and len(response.content) > 64:
                    return Reference(title, source, image.split("?")[0], response.content)
            except httpx.HTTPError:
                pass
            return None

        downloaded = await asyncio.gather(*(download(item) for item in found[: limit * 2]))
    return [r for r in downloaded if r][:limit]
