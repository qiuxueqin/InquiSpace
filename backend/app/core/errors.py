import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import JsonValue
from starlette.exceptions import HTTPException

from app.schemas.common import ErrorDetail, ErrorEnvelope

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        retryable: bool = False,
        details: dict[str, JsonValue] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details if details is not None else {}


def error_response(request: Request, status: int, error: ErrorDetail) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    body = ErrorEnvelope(error=error, request_id=request_id)
    return JSONResponse(
        status_code=status,
        content=body.model_dump(by_alias=True),
        headers={"X-Request-ID": request_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            request,
            exc.status_code,
            ErrorDetail(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo input values: validation failures may contain passwords or private text.
        details = [
            {"field": ".".join(map(str, item["loc"])), "type": item["type"]}
            for item in exc.errors()
        ]
        return error_response(
            request,
            422,
            ErrorDetail(
                code="VALIDATION_ERROR",
                message="请求参数不符合要求",
                details={"fields": details},
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        messages = {404: "资源不存在", 405: "请求方法不支持"}
        response = error_response(
            request,
            exc.status_code,
            ErrorDetail(
                code=f"HTTP_{exc.status_code}",
                message=messages.get(exc.status_code, "请求无法完成"),
            ),
        )
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled error request_id=%s type=%s", request.state.request_id, type(exc).__name__
        )
        return error_response(
            request,
            500,
            ErrorDetail(
                code="INTERNAL_ERROR",
                message="服务暂时不可用",
                retryable=True,
            ),
        )
