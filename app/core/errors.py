from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []


def error_payload(error: AppError) -> dict[str, object]:
    return {
        "success": False,
        "error": {
            "code": error.code,
            "message": error.message,
            "details": error.details,
        },
    }


async def handle_app_error(_request: Request, error: AppError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content=error_payload(error))


async def handle_validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
    details = [
        {"location": list(item["loc"]), "message": item["msg"], "type": item["type"]}
        for item in error.errors()
    ]
    app_error = AppError(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        details=details,
    )
    return JSONResponse(status_code=app_error.status_code, content=error_payload(app_error))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
