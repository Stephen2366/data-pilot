from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.common import ErrorResponse


class AppError(Exception):
    """业务异常基类。

    ★ 以后 API / Agent / Tool 层只要抛出 AppError 子类，就能统一变成稳定 JSON，
    不会把 Python traceback 泄露给调用方。
    """

    code = "app_error"
    message = "Application error."
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details


class NotFoundError(AppError):
    code = "not_found"
    message = "Resource not found."
    status_code = status.HTTP_404_NOT_FOUND


class ValidationAppError(AppError):
    code = "validation_error"
    message = "Request validation failed."
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT


class PermissionDeniedError(AppError):
    code = "permission_denied"
    message = "Permission denied."
    status_code = status.HTTP_403_FORBIDDEN


def get_trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "unknown")


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    trace_id: str,
    details: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        code=code,
        message=message,
        trace_id=trace_id,
        details=details,
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            trace_id=get_trace_id(request),
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=ValidationAppError.code,
            message=ValidationAppError.message,
            trace_id=get_trace_id(request),
            details=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Internal server error.",
            trace_id=get_trace_id(request),
            details=None,
        )
