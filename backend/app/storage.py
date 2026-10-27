"""Supabase Storage over its REST API: private `exports` (PDFs), public `covers`. Only the server holds this key."""

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

    async def signed_url(self, key: str, expires_in: int = 60, download_name: str | None = None) -> str:
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.post(f"{self.base}/object/sign/{BUCKET}/{quote(key)}",
                                       json={"expiresIn": expires_in}, headers=self.headers)
        response.raise_for_status()
        url = f"{self.base}{response.json()['signedURL']}"
        if download_name:
            url += f"&download={quote(download_name)}"
        return url

    async def delete(self, key: str) -> None:
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.request("DELETE", f"{self.base}/object/{BUCKET}",
                                          json={"prefixes": [key]}, headers=self.headers)
        response.raise_for_status()
