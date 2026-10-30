"""Pictures that cost us nothing, for the free preview: the Finder searches openly licensed images on the web
(Openverse, then Wikimedia Commons) and the free Illustrator paints on Cloudflare Workers AI's daily free
allowance. What they bring is kept in the library (public.assets, style key FREE_STYLE) for the next visitor.
Paid tomes never use these: they get the premium Illustrator (app.images)."""

import base64
import io
import logging

import httpx
from PIL import Image

from app.images import GeneratedImage
from app.llm import UpstreamError
from app.research import USER_AGENT, Photo

log = logging.getLogger("free_images")
FREE_STYLE = "free"  # style key of the free library
# What to ask Openverse for each kind of picture; colouring pages come out best as "coloring page".
QUERY = {"line_art": "{} coloring page", "colour": "{} illustration", "photo": "{}"}
CATEGORY = {"photo": "photograph"}  # few drawings carry Openverse's "illustration" category: search them all


class Finder:
    """Openverse search: only licences that allow commercial use and changes (we redraw to 1-bit), never mature
    results."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def find(self, subject: str, kind: str, accept=None) -> Photo | None:
        """The first result that loads, is big enough, looks like the kind asked for and passes `accept` (the
        Reviewer: does it show the subject?). An index of the whole web returns plenty of near misses."""
        async with httpx.AsyncClient(timeout=40, transport=self.transport, follow_redirects=True,
                                     headers={"User-Agent": USER_AGENT}) as http:
            try:
                r = await http.get("https://api.openverse.org/v1/images/", params={
                    "q": QUERY.get(kind, "{}").format(subject), "license_type": "commercial,modification", "mature": "false",
                    "page_size": 8,
                    **({"category": CATEGORY[kind]} if kind in CATEGORY else {})})
                r.raise_for_status()
                results = r.json().get("results") or []
            except (httpx.HTTPError, ValueError):
                return None
            for item in results:
                if (item.get("width") or 0) and (item.get("width") or 0) < 600:  # too small to print
                    continue
                try:
                    image = await http.get(item["url"])
                    image.raise_for_status()
                    picture = Image.open(io.BytesIO(image.content))
                    picture.load()
                except Exception:  # noqa: BLE001, S112  dead links and non-images are common in a web index
                    continue
                if kind == "line_art" and not looks_like_line_art(picture):
                    continue
                if accept is not None and not await accept(image.content):
                    continue
                media_type = image.headers.get("content-type", "image/jpeg").split(";")[0]
                return Photo(image.content, media_type if media_type in ("image/png", "image/jpeg") else "image/jpeg",
                             (item.get("creator") or "Autor desconocido")[:120],
                             f"CC {(item.get('license') or '').upper()} {item.get('license_version') or ''}".strip(),
                             item.get("foreign_landing_url") or item["url"])
        return None


def looks_like_line_art(picture: Image.Image) -> bool:
    """A colouring page is mostly white paper with dark, grey (not coloured) lines."""
    small = picture.convert("RGB").resize((128, 128))
    hsv = small.convert("HSV")
    white = sum(1 for v in small.convert("L").getdata() if v > 215) / (128 * 128)
    saturation = sum(px[1] for px in hsv.getdata()) / (128 * 128 * 255)
    return white > 0.55 and saturation < 0.15


class WorkersAI:
    """FLUX.1 schnell on Cloudflare Workers AI: free up to the account's daily allowance. Same call shape as the
    premium Illustrator, so the jobs can use either."""

    model = "@cf/black-forest-labs/flux-1-schnell"

    def __init__(self, account_id: str, token: str, *, timeout: float = 90,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.account_id, self.token, self.timeout, self.transport = account_id, token, timeout, transport

    async def generate(self, prompt: str, *, references: list[bytes] = (), aspect_ratio: str = "3:4",
                       resolution: str = "1K") -> GeneratedImage:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as http:
                response = await http.post(url, json={"prompt": prompt[:2048], "steps": 8},
                                           headers={"Authorization": f"Bearer {self.token}"})
        except httpx.HTTPError as exc:
            raise UpstreamError("upstream_unavailable", "Workers AI no respondió.") from exc
        if response.status_code >= 400:  # out of free allowance included: the preview just goes without
            raise UpstreamError("upstream_unavailable", f"Workers AI respondió {response.status_code}.")
        image = (response.json().get("result") or {}).get("image")
        if not image:
            raise UpstreamError("upstream_unavailable", "Workers AI no devolvió ninguna imagen.")
        return GeneratedImage(data=crop(base64.b64decode(image), aspect_ratio), media_type="image/jpeg",
                              model=self.model, cost_usd=0.0)


def crop(data: bytes, aspect_ratio: str) -> bytes:
    """FLUX schnell paints squares; pages and covers want their own aspect, cut from the centre."""
    w_ratio, h_ratio = (int(v) for v in aspect_ratio.split(":"))
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    if w * h_ratio > h * w_ratio:
        nw = h * w_ratio // h_ratio
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = w * h_ratio // w_ratio
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=92)
    return out.getvalue()
