import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.routes.crawl_jobs import router as crawl_jobs_router
from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.db.session import create_database_engine, create_session_factory

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.database_engine = create_database_engine(settings)
        app.state.session_factory = create_session_factory(app.state.database_engine)
        app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
        logger.info("application_started", extra={"environment": settings.environment})
        try:
            yield
        finally:
            await app.state.redis.aclose()
            await app.state.database_engine.dispose()
            logger.info("application_stopped")

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Company website crawling and intelligence API",
        lifespan=lifespan,
    )
    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(crawl_jobs_router)
    return application


app = create_app()
