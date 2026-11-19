from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, Request
from sqlalchemy import Engine

from anime_downloader.domain.model import MediaLocator
from anime_downloader.domain.ports import (
    AdapterRegistry as AdapterRegistryPort,
    Clock,
    IdGenerator,
    JobRepository,
    LibraryRepository,
    MediaDownloader,
    ProgressCallback,
)
from anime_downloader.infrastructure.adapter_registry import AdapterRegistry
from anime_downloader.infrastructure.clock import SystemClock
from anime_downloader.infrastructure.db.session import (
    create_engine_for_path,
    make_session_factory,
)
from anime_downloader.infrastructure.anime_sama import AnimeSamaAdapter
from anime_downloader.infrastructure.http_downloader import HttpMediaDownloader
from anime_downloader.infrastructure.ids import UuidIdGenerator
from anime_downloader.infrastructure.persistence.job_repository import (
    SqlAlchemyJobRepository,
)
from anime_downloader.infrastructure.persistence.library_repository import (
    SqlAlchemyLibraryRepository,
)
from anime_downloader.infrastructure.worker import DownloadWorker
from anime_downloader.infrastructure.yt_dlp_downloader import YtDlpMediaDownloader


def _is_hls_or_dash_url(url: str) -> bool:
    lowered = url.lower()
    path = (urlparse(url).path or "").lower()
    return (
        path.endswith(".m3u8")
        or path.endswith(".m3u")
        or path.endswith(".mpd")
        or "m3u8" in lowered
        or "/hls" in lowered
    )


class DefaultMediaDownloader:
    def __init__(
        self,
        http_downloader: HttpMediaDownloader | None = None,
        ytdlp_downloader: YtDlpMediaDownloader | None = None,
    ) -> None:
        self._http = (
            http_downloader if http_downloader is not None else HttpMediaDownloader()
        )
        self._ytdlp = (
            ytdlp_downloader if ytdlp_downloader is not None else YtDlpMediaDownloader()
        )

    def download(
        self,
        media: MediaLocator,
        destination: str,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> str:
        if _is_hls_or_dash_url(media.url):
            return self._ytdlp.download(
                media, destination, on_progress=on_progress
            )
        return self._http.download(media, destination, on_progress=on_progress)


@dataclass
class AppContainer:
    data_dir: Path
    library_root: Path
    engine: Engine
    jobs: JobRepository
    library: LibraryRepository
    registry: AdapterRegistryPort
    ids: IdGenerator
    downloader: MediaDownloader
    worker: DownloadWorker
    clock: Clock


def build_default_registry() -> AdapterRegistryPort:
    return AdapterRegistry([AnimeSamaAdapter()])


def build_container(
    data_dir: Path,
    *,
    registry: AdapterRegistryPort | None = None,
    downloader: MediaDownloader | None = None,
    worker_sleep: Callable[[float], None] | None = None,
) -> AppContainer:
    db_path = data_dir / "app.db"
    library_root = data_dir / "library"
    engine = create_engine_for_path(db_path)
    session_factory = make_session_factory(engine)
    jobs = SqlAlchemyJobRepository(session_factory)
    library = SqlAlchemyLibraryRepository(session_factory)
    resolved_registry = registry if registry is not None else build_default_registry()
    ids = UuidIdGenerator()
    resolved_downloader = (
        downloader if downloader is not None else DefaultMediaDownloader()
    )
    worker = DownloadWorker(
        jobs=jobs,
        library=library,
        registry=resolved_registry,
        downloader=resolved_downloader,
        library_root=library_root,
        sleep=worker_sleep if worker_sleep is not None else time.sleep,
        ids=ids,
    )
    return AppContainer(
        data_dir=data_dir,
        library_root=library_root,
        engine=engine,
        jobs=jobs,
        library=library,
        registry=resolved_registry,
        ids=ids,
        downloader=resolved_downloader,
        worker=worker,
        clock=SystemClock(),
    )


def get_container(request: Request) -> AppContainer:
    container: AppContainer | None = getattr(request.app.state, "container", None)
    if container is None:
        init_fn = request.app.state.init_container
        container = init_fn()
    return container


def get_registry(
    container: Annotated[AppContainer, Depends(get_container)],
) -> AdapterRegistryPort:
    return container.registry


def get_job_repository(
    container: Annotated[AppContainer, Depends(get_container)],
) -> JobRepository:
    return container.jobs


def get_library_repository(
    container: Annotated[AppContainer, Depends(get_container)],
) -> LibraryRepository:
    return container.library


def get_id_generator(
    container: Annotated[AppContainer, Depends(get_container)],
) -> IdGenerator:
    return container.ids


def get_worker(
    container: Annotated[AppContainer, Depends(get_container)],
) -> DownloadWorker:
    return container.worker


def get_clock(
    container: Annotated[AppContainer, Depends(get_container)],
) -> Clock:
    return container.clock
