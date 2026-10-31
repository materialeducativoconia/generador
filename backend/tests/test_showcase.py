import io

from PIL import Image

from app import showcase
from app.images import GeneratedImage


class Images:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, **kw):
        self.prompts.append(prompt)
        buf = io.BytesIO()
        Image.new("RGB", (60, 80), "#7fc8a9").save(buf, "PNG")
        return GeneratedImage(data=buf.getvalue(), media_type="image/png", model="fake", cost_usd=0.09)


class Storage:
    def __init__(self):
        self.uploads = {}

    async def upload(self, key, data, content_type="application/pdf", bucket="exports"):
        self.uploads[(bucket, key)] = (data, content_type)

    def public_url(self, key, bucket="covers"):
        return f"https://storage.test/{bucket}/{key}"


async def test_the_worker_paints_only_the_example_covers_still_missing(monkeypatch):
    have = {"https://storage.test/covers/showcase/colorear-dinosaurios.webp"}

    async def exists(url):
        return url in have

    monkeypatch.setattr(showcase, "_exists", exists)
    monkeypatch.setattr(showcase, "COVERS", showcase.COVERS[:2])
    images, storage = Images(), Storage()

    assert await showcase.paint_missing(images, storage) == 1
    assert len(images.prompts) == 1 and "pencil" in images.prompts[0]
    data, kind = storage.uploads[("covers", "showcase/escritura-letras.webp")]
    assert kind == "image/webp" and Image.open(io.BytesIO(data)).format == "WEBP"
