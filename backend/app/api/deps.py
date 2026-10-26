import uuid

from fastapi import Request

from app.auth import InvalidToken
from app.errors import ApiError


def current_user_id(request: Request) -> uuid.UUID:
    # Sync on purpose: fetching the JWKS is blocking I/O, so FastAPI runs this in its threadpool.
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "unauthorized", "Falta el token de acceso.")
    try:
        return request.app.state.verifier.user_id(token)
    except InvalidToken:
        raise ApiError(401, "unauthorized", "El token de acceso no es válido o ha caducado.")
