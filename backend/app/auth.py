import uuid

import jwt


class InvalidToken(Exception):
    pass


class TokenVerifier:
    """Verifies Supabase Auth access tokens locally against the project's JWKS (ES256)."""

    def __init__(self, jwks_url: str, issuer: str, audience: str = "authenticated") -> None:
        # Keys are cached for 10 min, so a brief JWKS outage doesn't stop the API.
        self._jwks = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=600)
        self._issuer = issuer
        self._audience = audience

    def user_id(self, token: str) -> uuid.UUID:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
            return uuid.UUID(claims["sub"])
        except (jwt.PyJWTError, ValueError) as exc:
            raise InvalidToken(str(exc)) from exc
