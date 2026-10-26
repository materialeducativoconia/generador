"""Signs tokens the way Supabase Auth does (ES256 + JWKS) so tests exercise real signature checks."""

import contextlib
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

SUPABASE_URL = "https://test-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"


class SigningKey:
    def __init__(self) -> None:
        self.kid = str(uuid.uuid4())
        self.private_key = ec.generate_private_key(ec.SECP256R1())

    def jwk(self) -> dict:
        jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(self.private_key.public_key()))
        return {**jwk, "kid": self.kid, "alg": "ES256", "use": "sig"}

    def token(self, sub: str, *, aud: str = "authenticated", iss: str = ISSUER, expires_in: int = 3600) -> str:
        now = int(time.time())
        claims = {"sub": sub, "aud": aud, "iss": iss, "iat": now, "exp": now + expires_in, "role": "authenticated"}
        return jwt.encode(claims, self.private_key, algorithm="ES256", headers={"kid": self.kid})


@contextlib.contextmanager
def serve_jwks(*keys: SigningKey):
    """Serves a JWKS document over local HTTP, like Supabase's /.well-known/jwks.json, and yields its URL."""
    body = json.dumps({"keys": [k.jwk() for k in keys]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/auth/v1/.well-known/jwks.json"
    finally:
        server.shutdown()
        server.server_close()
