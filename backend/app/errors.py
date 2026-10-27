from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Renders as the uniform error body from ARCHITECTURE.md §3: {"error": {"code", "message"}}."""

    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        error = {"code": exc.code, "message": exc.message}
        if exc.details:
            error["details"] = exc.details
        return JSONResponse({"error": error}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = {".".join(str(p) for p in e["loc"][1:]): e["msg"] for e in exc.errors()}
        return JSONResponse(
            {"error": {"code": "validation_error", "message": "Revisa los datos enviados.", "details": fields}},
            status_code=422,
        )
