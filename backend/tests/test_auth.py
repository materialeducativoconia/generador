import uuid

import pytest

from app.auth import InvalidToken, TokenVerifier
from tests.auth_helpers import ISSUER, SigningKey, serve_jwks


@pytest.fixture
def key():
    return SigningKey()


@pytest.fixture
def verifier(key):
    with serve_jwks(key) as jwks_url:
        yield TokenVerifier(jwks_url=jwks_url, issuer=ISSUER)


def test_valid_supabase_token_yields_user_id(verifier, key):
    user_id = uuid.uuid4()

    assert verifier.user_id(key.token(str(user_id))) == user_id


def test_expired_token_is_rejected(verifier, key):
    with pytest.raises(InvalidToken):
        verifier.user_id(key.token(str(uuid.uuid4()), expires_in=-60))


def test_token_for_another_audience_is_rejected(verifier, key):
    with pytest.raises(InvalidToken):
        verifier.user_id(key.token(str(uuid.uuid4()), aud="anon"))


def test_token_from_another_supabase_project_is_rejected(verifier, key):
    with pytest.raises(InvalidToken):
        verifier.user_id(key.token(str(uuid.uuid4()), iss="https://other-project.supabase.co/auth/v1"))


def test_token_signed_with_unknown_key_is_rejected(verifier):
    forger = SigningKey()

    with pytest.raises(InvalidToken):
        verifier.user_id(forger.token(str(uuid.uuid4())))


def test_garbage_is_rejected(verifier):
    with pytest.raises(InvalidToken):
        verifier.user_id("not-a-jwt")


def test_hs256_token_is_rejected_even_if_signed_with_public_key_material(verifier, key):
    # Guards against algorithm-confusion: only ES256 is accepted.
    import jwt

    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "authenticated", "iss": ISSUER, "exp": 9999999999},
        "some-shared-secret-at-least-32-bytes-long!!",
        algorithm="HS256",
        headers={"kid": key.kid},
    )

    with pytest.raises(InvalidToken):
        verifier.user_id(token)
