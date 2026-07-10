from typing import Any, Literal

from pydantic import BaseModel, Field


class SuccessResponse[DataT](BaseModel):
    success: Literal[True] = True
    data: DataT


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    error: ErrorDetail
