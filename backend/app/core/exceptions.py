from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error_code": exc.error_code, "message": exc.message},
    )


async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"success": False, "error_code": "INTERNAL_ERROR", "message": "服务器内部错误"},
    )


def ok(data=None, message: str = "ok") -> dict:
    return {"success": True, "data": data if data is not None else {}, "message": message}
