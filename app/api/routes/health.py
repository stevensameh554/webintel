import asyncio
from typing import Literal, TypedDict

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

router = APIRouter(tags=["health"])


class CheckResult(TypedDict):
    status: Literal["up", "down"]
    detail: str | None


async def check_postgresql(engine: AsyncEngine) -> CheckResult:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"status": "up", "detail": None}
    except Exception as exc:
        return {"status": "down", "detail": type(exc).__name__}


async def check_redis(client: Redis) -> CheckResult:
    try:
        await client.ping()
        return {"status": "up", "detail": None}
    except Exception as exc:
        return {"status": "down", "detail": type(exc).__name__}


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return {
        "success": True,
        "data": {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
        },
    }


@router.get("/ready")
async def readiness(request: Request) -> JSONResponse:
    timeout = request.app.state.settings.readiness_timeout_seconds
    try:
        postgresql, redis = await asyncio.wait_for(
            asyncio.gather(
                check_postgresql(request.app.state.database_engine),
                check_redis(request.app.state.redis),
            ),
            timeout=timeout,
        )
    except TimeoutError:
        postgresql = {"status": "down", "detail": "readiness timeout"}
        redis = {"status": "down", "detail": "readiness timeout"}

    checks = {"postgresql": postgresql, "redis": redis}
    is_ready = all(check["status"] == "up" for check in checks.values())
    payload = {
        "success": is_ready,
        "data": {"status": "ready" if is_ready else "not_ready", "checks": checks},
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )
