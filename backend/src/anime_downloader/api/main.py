from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from anime_downloader.api.deps import AppContainer, build_container
from anime_downloader.api.routes_jobs import router as jobs_router
from anime_downloader.api.routes_library import router as library_router
from anime_downloader.domain.errors import (
    DiscoveryFailed,
    DomainError,
    InvalidSourceUrl,
    JobNotFound,
    NoAdapterFound,
    JobCannotBeDismissed,
    NoFailedEpisodes,
    SeasonNotFound,
)
from anime_downloader.domain.ports import AdapterRegistry, MediaDownloader
from anime_downloader.infrastructure.db.session import run_migrations
from anime_downloader.infrastructure.library_migrator import migrate_library

logger = logging.getLogger(__name__)


def _resolve_cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "*")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["*"]


def _status_for_domain_error(exc: DomainError) -> int:
    if isinstance(exc, (InvalidSourceUrl, NoAdapterFound)):
        return status.HTTP_400_BAD_REQUEST
    if isinstance(exc, (JobNotFound, SeasonNotFound)):
        return status.HTTP_404_NOT_FOUND
    if isinstance(exc, (NoFailedEpisodes, JobCannotBeDismissed)):
        return status.HTTP_409_CONFLICT
    if isinstance(exc, DiscoveryFailed):
        return status.HTTP_502_BAD_GATEWAY
    return status.HTTP_400_BAD_REQUEST


def create_app(
    data_dir: str | Path | None = None,
    *,
    registry: AdapterRegistry | None = None,
    downloader: MediaDownloader | None = None,
    worker_sleep: Callable[[float], None] | None = None,
) -> FastAPI:
    def _init_container() -> AppContainer:
        resolved_dir = (
            Path(data_dir)
            if data_dir is not None
            else Path(os.environ.get("DATA_DIR", "/data"))
        )
        run_migrations(resolved_dir / "app.db")
        container = build_container(
            resolved_dir,
            registry=registry,
            downloader=downloader,
            worker_sleep=worker_sleep,
        )
        fastapi_app.state.container = container
        return container

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        container = app_instance.state.init_container()
        report = migrate_library(
            library=container.library,
            registry=container.registry,
            library_root=container.library_root,
        )
        logger.info(
            "Library migration finished: renamed_files=%s merged_series=%s errors=%s",
            report.renamed_files,
            report.merged_series,
            report.errors,
        )
        container.worker.resume_incomplete()
        container.worker.start_background()
        try:
            yield
        finally:
            container.worker.stop()
            container.engine.dispose()
            app_instance.state.container = None

    fastapi_app = FastAPI(
        title="Anime Downloader API",
        version="0.1.0",
        lifespan=lifespan,
    )
    fastapi_app.state.container = None
    fastapi_app.state.init_container = _init_container

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_cors_origins(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @fastapi_app.exception_handler(DomainError)
    async def handle_domain_error(
        request: Request, exc: DomainError
    ) -> JSONResponse:
        _ = request
        return JSONResponse(
            status_code=_status_for_domain_error(exc),
            content={"detail": str(exc)},
        )

    fastapi_app.include_router(jobs_router)
    fastapi_app.include_router(library_router)
    return fastapi_app


app = create_app()
