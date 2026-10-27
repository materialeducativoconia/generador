"""The Researcher's sources: Wikipedia for facts, Wikimedia Commons for freely licensed photos.

Everything here is best effort: no source means the tome is written as before, never a failed job.
Fetched text is untrusted data; the fact-sheet prompt treats it as such.
"""

import asyncio
import html
import re
from dataclasses import dataclass

import httpx

USER_AGENT = "MaterialEducativoIA/1.0 (+https://github.com/materialeducativoconia)"
# Printable and redistributable without asking: public domain, CC0, CC BY, CC BY-SA. No NC/ND.
FREE_LICENSE = re.compile(r"^(cc0|pd|public domain|cc-by(-sa)?-\d)", re.I)


@dataclass
class Document:
    title: str
    url: str
    text: str


@dataclass
class Photo:
    data: bytes
    media_type: str
    author: str
    license: str
    source_url: str

    @property
    def credit(self) -> str:
        return f"Foto: {self.author}, {self.license}, Wikimedia Commons"


class Web:
    def __init__(self, *, timeout: float = 15, transport: httpx.AsyncBaseTransport | None = None):
        self.timeout, self.transport = timeout, transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self.transport, follow_redirects=True,
                                 headers={"User-Agent": USER_AGENT})

    async def wikipedia(self, queries: list[str], *, lang: str = "es", per_query: int = 2,
                        max_chars: int = 6000) -> list[Document]:
        api = f"https://{lang.split('-')[0]}.wikipedia.org/w/api.php"
        async with self._client() as http:
            titles: list[str] = []
            for query in queries:
                try:
                    r = await http.get(api, params={"action": "query", "list": "search", "srsearch": query,
                                                    "srlimit": per_query, "format": "json"})
                    r.raise_for_status()
                    titles += [h["title"] for h in r.json()["query"]["search"] if h["title"] not in titles]
                except (httpx.HTTPError, ValueError, KeyError):
                    continue

            async def extract(title: str) -> Document | None:
                try:
                    r = await http.get(api, params={"action": "query", "prop": "extracts|info", "inprop": "url",
                                                    "explaintext": 1, "titles": title,
                                                    "redirects": 1, "format": "json"})
                    r.raise_for_status()
                    page = next(iter(r.json()["query"]["pages"].values()))
                    text = page.get("extract") or ""
                    # exchars caps at 1200, so the whole article comes back and is cut here.
                    return Document(page["title"], page["fullurl"], text[:max_chars]) if text else None
                except (httpx.HTTPError, ValueError, KeyError, StopIteration):
                    return None

            docs = await asyncio.gather(*(extract(t) for t in titles[:6]))
        return [d for d in docs if d]

    async def commons_photo(self, query: str) -> Photo | None:
        async with self._client() as http:
            try:
                r = await http.get("https://commons.wikimedia.org/w/api.php", params={
                    "action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
                    "gsrnamespace": 6, "gsrlimit": 10, "prop": "imageinfo", "iiprop": "url|extmetadata|mime",
                    "iiurlwidth": 1600, "format": "json"})
                r.raise_for_status()
                pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
            except (httpx.HTTPError, ValueError):
                return None
            for page in pages:
                info = (page.get("imageinfo") or [{}])[0]
                meta = info.get("extmetadata", {})
                license_code = (meta.get("License") or {}).get("value") or ""
                if info.get("mime") not in ("image/jpeg", "image/png") or not FREE_LICENSE.match(license_code):
                    continue
                try:
                    image = await http.get(info["thumburl"])
                    image.raise_for_status()
                except (httpx.HTTPError, KeyError):
                    continue
                author = _plain((meta.get("Artist") or {}).get("value") or "") or "Autor desconocido"
                return Photo(image.content, info["mime"], author[:120],
                             (meta.get("LicenseShortName") or {}).get("value") or license_code.upper(),
                             info.get("descriptionurl", ""))
        return None


def _plain(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())
