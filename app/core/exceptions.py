"""统一异常处理模块：业务异常基类 + 三层异常兜底注册。

★ 类比 SpringBoot 的 @RestControllerAdvice + @ExceptionHandler：
任何异常都变成统一的 JSON 响应（code/message/trace_id/details），
不把 Python traceback 泄露给调用方。
"""

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
    """资源不存在 → HTTP 404。"""

    code = "not_found"
    message = "Resource not found."
    status_code = status.HTTP_404_NOT_FOUND


class ValidationAppError(AppError):
    """请求参数校验失败 → HTTP 422（分页参数越界等都会落到这里）。"""

    code = "validation_error"
    message = "Request validation failed."
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT


class PermissionDeniedError(AppError):
    """无权限访问 → HTTP 403，后续 RBAC / SQL Guard 的越权拦截会复用它。"""

    code = "permission_denied"
    message = "Permission denied."
    status_code = status.HTTP_403_FORBIDDEN


def get_trace_id(request: Request) -> str:
    """从请求上下文读取日志中间件写入的 trace_id。

    极端情况（中间件未执行）兜底返回 "unknown"，保证异常处理器不会因取不到 trace_id 而报错。
    """
    return getattr(request.state, "trace_id", "unknown")


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    trace_id: str,
    details: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """把错误信息组装成统一的 ErrorResponse JSON。

    ★ 所有异常出口都必须经过这一个函数，保证错误响应永远是
    `code / message / trace_id / details` 四件套，前端和评测脚本只写一套解析逻辑。
    """

    body = ErrorResponse(
        code=code,
        message=message,
        trace_id=trace_id,
        details=details,
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    """注册三层异常兜底，类比 SpringBoot 的 @RestControllerAdvice + @ExceptionHandler。

    ★ 捕获从“最具体”到“最兜底”：业务异常 AppError → FastAPI 参数校验错误 → 未知
    Exception。目标只有一个：任何错误都变成统一 JSON，不把 traceback 泄露给调用方。
    """

    # 第 1 层：业务异常。抛出哪个子类，就用它自带的 code / message / status_code。
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            trace_id=get_trace_id(request),
            details=exc.details,
        )

    # 第 2 层：FastAPI 参数校验失败（如 page=0）。details 会带上具体哪个字段错在哪。
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

    # 第 3 层：未知异常兜底。对外只说 internal_error，细节留在服务端日志里排查。
    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Internal server error.",
            trace_id=get_trace_id(request),
            details=None,
        )
