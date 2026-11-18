from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
import threading
from urllib.error import HTTPError

import pytest

from anime_downloader.domain.model import (
    DownloadJob,
    Episode,
    EpisodeStatus,
    JobStatus,
    MediaLocator,
    Season,
    Series,
)
from anime_downloader.infrastructure.clock import SystemClock
from anime_downloader.infrastructure.db.base import Base
from anime_downloader.infrastructure.db.models import (
    EpisodeRow,
    JobRow,
    SeasonRow,
    SeriesRow,
)
from anime_downloader.infrastructure.db.session import (
    create_engine_for_path,
    make_session_factory,
    run_migrations,
)
from anime_downloader.infrastructure.http_downloader import (
    FakeMediaDownloader,
    HttpMediaDownloader,
)
from anime_downloader.infrastructure.ids import UuidIdGenerator
from anime_downloader.infrastructure.persistence.job_repository import (
    SqlAlchemyJobRepository,
)
from anime_downloader.infrastructure.persistence.library_repository import (
    SqlAlchemyLibraryRepository,
)


@pytest.fixture
def session_factory(tmp_path: Path):
    db_path = tmp_path / "nested" / "app.db"
    run_migrations(str(db_path))
    engine = create_engine_for_path(str(db_path))
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


def test_orm_metadata_defines_expected_tables() -> None:
    assert {
        SeriesRow.__tablename__,
        SeasonRow.__tablename__,
        EpisodeRow.__tablename__,
        JobRow.__tablename__,
    } == {"series", "seasons", "episodes", "jobs"}
    assert set(Base.metadata.tables.keys()) == {
        "series",
        "seasons",
        "episodes",
        "jobs",
    }


def test_run_migrations_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "idempotent.db"
    run_migrations(str(db_path))
    run_migrations(str(db_path))
    assert db_path.exists()


def test_library_repository_upserts_and_lists_hierarchy(session_factory) -> None:
    repo = SqlAlchemyLibraryRepository(session_factory)

    series = repo.upsert_series(Series(id="ser-1", title="Frieren"))
    season_2 = repo.upsert_season(Season(id="sea-2", series_id=series.id, number=2))
    season_1 = repo.upsert_season(Season(id="sea-1", series_id=series.id, number=1))

    ep_2 = repo.upsert_episode(
        Episode(
            id="ep-2",
            season_id=season_1.id,
            number=2,
            title="Episode Two",
            status=EpisodeStatus.PENDING,
            source_url="https://demo.local/season/frieren/1/e/2",
        )
    )
    ep_1 = repo.upsert_episode(
        Episode(
            id="ep-1",
            season_id=season_1.id,
            number=1,
            title="Episode One",
            status=EpisodeStatus.PENDING,
            source_url="https://demo.local/season/frieren/1/e/1",
        )
    )

    assert repo.list_series() == [Series(id="ser-1", title="Frieren")]
    assert repo.list_seasons(series.id) == [season_1, season_2]
    assert repo.list_episodes(season_1.id) == [ep_1, ep_2]
    assert repo.list_episodes(season_2.id) == []


def test_library_repository_updates_episode_and_lists_failed(session_factory) -> None:
    repo = SqlAlchemyLibraryRepository(session_factory)
    series = repo.upsert_series(Series(id="ser-1", title="Orb"))
    season = repo.upsert_season(Season(id="sea-1", series_id=series.id, number=1))

    repo.upsert_episode(
        Episode(
            id="ep-1",
            season_id=season.id,
            number=1,
            title="Ep 1",
            status=EpisodeStatus.PENDING,
            source_url="https://demo.local/season/orb/1/e/1",
        )
    )
    repo.upsert_episode(
        Episode(
            id="ep-2",
            season_id=season.id,
            number=2,
            title="Ep 2",
            status=EpisodeStatus.PENDING,
            source_url="https://demo.local/season/orb/1/e/2",
        )
    )

    completed = repo.upsert_episode(
        Episode(
            id="ep-1",
            season_id=season.id,
            number=1,
            title="Ep 1",
            status=EpisodeStatus.COMPLETED,
            source_url="https://demo.local/season/orb/1/e/1",
            file_path="/data/library/Orb/1/E01 - Ep 1.mp4",
        )
    )
    failed = repo.upsert_episode(
        Episode(
            id="ep-2",
            season_id=season.id,
            number=2,
            title="Ep 2",
            status=EpisodeStatus.FAILED,
            source_url="https://demo.local/season/orb/1/e/2",
            error_message="network timeout",
        )
    )

    assert repo.get_episode("ep-1") == completed
    assert repo.get_episode("missing") is None
    assert repo.list_failed_episodes(season.id) == [failed]


def test_library_repository_deduplicates_natural_keys_on_re_discovery(
    session_factory,
) -> None:
    repo = SqlAlchemyLibraryRepository(session_factory)

    first_series = repo.upsert_series(Series(id="ser-a", title="Dungeon Meshi"))
    second_series = repo.upsert_series(Series(id="ser-b", title="Dungeon Meshi"))
    assert second_series == first_series
    assert repo.list_series() == [first_series]

    first_season = repo.upsert_season(
        Season(id="sea-a", series_id=first_series.id, number=1)
    )
    second_season = repo.upsert_season(
        Season(id="sea-b", series_id=first_series.id, number=1)
    )
    assert second_season == first_season
    assert repo.list_seasons(first_series.id) == [first_season]

    first_ep = repo.upsert_episode(
        Episode(
            id="ep-a",
            season_id=first_season.id,
            number=1,
            title="Hot Pot",
            status=EpisodeStatus.PENDING,
            source_url="https://demo.local/season/meshi/1/e/1",
        )
    )
    second_ep = repo.upsert_episode(
        Episode(
            id="ep-b",
            season_id=first_season.id,
            number=1,
            title="Hot Pot Updated",
            status=EpisodeStatus.COMPLETED,
            source_url="https://demo.local/season/meshi/1/e/1",
            file_path="/data/library/Dungeon Meshi/1/E01.mp4",
        )
    )
    assert second_ep.id == first_ep.id
    assert second_ep.title == "Hot Pot Updated"
    assert second_ep.status == EpisodeStatus.COMPLETED
    assert len(repo.list_episodes(first_season.id)) == 1


def test_job_repository_saves_updates_and_filters_resumable(session_factory) -> None:
    repo = SqlAlchemyJobRepository(session_factory)

    pending_job = DownloadJob(
        id="job-pending",
        source_url="https://demo.local/season/show-a/1",
        adapter_id="demo",
        status=JobStatus.PENDING,
        series_id="ser-1",
        season_id="sea-1",
        total_episodes=3,
    )
    running_job = DownloadJob(
        id="job-running",
        source_url="https://demo.local/season/show-b/1",
        adapter_id="demo",
        status=JobStatus.RUNNING,
        total_episodes=3,
        completed_episodes=1,
    )
    completed_job = DownloadJob(
        id="job-completed",
        source_url="https://demo.local/season/show-c/1",
        adapter_id="demo",
        status=JobStatus.COMPLETED,
        total_episodes=3,
        completed_episodes=3,
    )
    failed_job = DownloadJob(
        id="job-failed",
        source_url="https://demo.local/season/show-d/1",
        adapter_id="demo",
        status=JobStatus.FAILED,
        error_message="adapter failed",
    )

    for job in (pending_job, running_job, completed_job, failed_job):
        repo.save(job)

    assert repo.get("job-pending") == pending_job
    assert repo.get("unknown-job") is None
    assert len(repo.list_jobs()) == 4

    resumable = repo.list_resumable()
    assert {job.id for job in resumable} == {"job-pending", "job-running"}
    assert all(
        job.status in {JobStatus.PENDING, JobStatus.RUNNING} for job in resumable
    )

    updated = DownloadJob(
        id="job-pending",
        source_url=pending_job.source_url,
        adapter_id="demo",
        status=JobStatus.COMPLETED,
        series_id="ser-1",
        season_id="sea-1",
        total_episodes=3,
        completed_episodes=3,
        failed_episodes=0,
    )
    repo.save(updated)
    assert repo.get("job-pending") == updated
    assert [job.id for job in repo.list_resumable()] == ["job-running"]


def test_job_repository_persists_dismissed_at(session_factory) -> None:
    repo = SqlAlchemyJobRepository(session_factory)
    job = DownloadJob(
        id="job-dismissed",
        source_url="https://demo.local/season/show/1",
        adapter_id="demo",
        status=JobStatus.COMPLETED,
        total_episodes=1,
        completed_episodes=1,
        dismissed_at="2026-11-18T12:00:00+00:00",
    )
    repo.save(job)
    loaded = repo.get("job-dismissed")
    assert loaded is not None
    assert loaded.dismissed_at == "2026-11-18T12:00:00+00:00"


def test_fake_media_downloader_writes_minimal_bytes_and_creates_parents(
    tmp_path: Path,
) -> None:
    downloader = FakeMediaDownloader()
    dest = tmp_path / "library" / "demo-show" / "1" / "E01.mp4"
    locator = MediaLocator(url="https://demo.local/media/1.mp4", suggested_filename="E01.mp4")

    written_path = downloader.download(locator, str(dest))

    assert written_path == str(dest.resolve())
    assert dest.exists()
    assert len(dest.read_bytes()) > 0


def test_http_media_downloader_streams_get_with_headers_and_creates_parents(
    tmp_path: Path,
) -> None:
    received_headers: dict[str, str] = {}
    payload = b"video-stream-bytes-" * 1024

    class FastLocalHTTPServer(ThreadingHTTPServer):
        def server_bind(self) -> None:
            TCPServer.server_bind(self)
            host, port = self.server_address[:2]
            self.server_name = str(host)
            self.server_port = int(port)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            received_headers["X-Custom-Token"] = self.headers.get("X-Custom-Token", "")
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = FastLocalHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        host, port = server.server_address[:2]
        locator = MediaLocator(
            url=f"http://{host}:{port}/media/1.mp4",
            suggested_filename="E01.mp4",
            headers={"X-Custom-Token": "secret-123"},
        )
        dest = tmp_path / "downloads" / "series" / "1" / "E01.mp4"
        downloader = HttpMediaDownloader()

        written_path = downloader.download(locator, str(dest))

        assert written_path == str(dest.resolve())
        assert dest.read_bytes() == payload
        assert received_headers["X-Custom-Token"] == "secret-123"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_media_downloader_cleans_up_temp_file_on_http_error(
    tmp_path: Path,
) -> None:
    class FastLocalHTTPServer(ThreadingHTTPServer):
        def server_bind(self) -> None:
            TCPServer.server_bind(self)
            host, port = self.server_address[:2]
            self.server_name = str(host)
            self.server_port = int(port)

    class ErrorHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = FastLocalHTTPServer(("127.0.0.1", 0), ErrorHandler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        host, port = server.server_address[:2]
        locator = MediaLocator(url=f"http://{host}:{port}/missing.mp4")
        dest_dir = tmp_path / "downloads"
        dest = dest_dir / "E01.mp4"
        downloader = HttpMediaDownloader()

        with pytest.raises(HTTPError):
            downloader.download(locator, str(dest))

        assert not dest.exists()
        assert list(dest_dir.iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_clock_and_id_generator() -> None:
    clock = SystemClock()
    parsed = datetime.fromisoformat(clock.now_iso())
    assert parsed.tzinfo is not None

    ids = UuidIdGenerator()
    first = ids.new_id()
    second = ids.new_id()
    assert first != second
    assert len(first) == 36
