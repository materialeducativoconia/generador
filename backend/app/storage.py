"""Supabase Storage over its REST API: private `exports` (PDFs) and `references` (style uploads), public
`covers` and `images`. Only the server holds this key."""

from urllib.parse import quote

import httpx

BUCKET = "exports"


class Storage:
    def __init__(self, supabase_url: str, service_key: str):
        self.base = f"{supabase_url.rstrip('/')}/storage/v1"
        self.headers = {"apikey": service_key}
        if service_key.startswith("eyJ"):  # legacy service_role JWT; new sb_secret_ keys go in apikey only
            self.headers["Authorization"] = f"Bearer {service_key}"

    async def upload(self, key: str, data: bytes, content_type: str = "application/pdf", bucket: str = BUCKET) -> None:
        async with httpx.AsyncClient(timeout=60) as http:
            response = await http.post(f"{self.base}/object/{bucket}/{quote(key)}", content=data,
                                       headers={**self.headers, "Content-Type": content_type, "x-upsert": "true"})
        response.raise_for_status()

    def public_url(self, key: str, bucket: str = "covers") -> str:
        return f"{self.base}/object/public/{bucket}/{quote(key)}"

    async def download(self, key: str, bucket: str = "covers") -> bytes:
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.get(self.public_url(key, bucket))
        response.raise_for_status()
        return response.content

    async def upload_url(self, key: str, bucket: str) -> str:
        """A one-off URL the browser PUTs a file to, so big reference PDFs never pass through our server."""
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.post(f"{self.base}/object/upload/sign/{bucket}/{quote(key)}",
                                       headers={**self.headers, "x-upsert": "true"})
        response.raise_for_status()
        return f"{self.base}{response.json()['url']}"

    async def download_private(self, key: str, bucket: str) -> bytes:
        async with httpx.AsyncClient(timeout=120) as http:
            response = await http.get(f"{self.base}/object/{bucket}/{quote(key)}", headers=self.headers)
        response.raise_for_status()
        return response.content

    async def signed_url(self, key: str, expires_in: int = 60, download_name: str | None = None,
                         bucket: str = BUCKET) -> str:
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.post(f"{self.base}/object/sign/{bucket}/{quote(key)}",
                                       json={"expiresIn": expires_in}, headers=self.headers)
        response.raise_for_status()
        url = f"{self.base}{response.json()['signedURL']}"
        if download_name:
            url += f"&download={quote(download_name)}"
        return url

    async def signed_urls(self, keys: list[str], bucket: str, expires_in: int = 3600) -> dict[str, str]:
        """Many private files in one call (the style library shows three previews per style)."""
        if not keys:
            return {}
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.post(f"{self.base}/object/sign/{bucket}", headers=self.headers,
                                       json={"expiresIn": expires_in, "paths": keys})
        response.raise_for_status()
        return {r["path"]: f"{self.base}{r['signedURL']}" for r in response.json() if r.get("signedURL")}

    async def delete(self, key: str, bucket: str = BUCKET) -> None:
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.request("DELETE", f"{self.base}/object/{bucket}",
                                          json={"prefixes": [key]}, headers=self.headers)
        response.raise_for_status()
