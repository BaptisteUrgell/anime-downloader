from __future__ import annotations

import ast
from pathlib import Path

import pytest

from anime_downloader.application.retry_failed import retry_failed
from anime_downloader.application.start_season_download import start_season_download
from anime_downloader.domain.model import (
    DownloadJob,
    Episode,
    EpisodeRef,
    EpisodeStatus,
    JobStatus,
    MediaLocator,
    Season,
    SeasonDiscovery,
    Series,
    SourceUrl,
)
from anime_downloader.infrastructure.adapter_registry import AdapterRegistry
from anime_downloader.infrastructure.db.session import (
    create_engine_for_path,
    make_session_factory,
    run_migrations,
)
from anime_downloader.infrastructure.demo_adapter import DemoAdapter
from anime_downloader.infrastructure.http_downloader import FakeMediaDownloader
from anime_downloader.infrastructure.ids import UuidIdGenerator
from anime_downloader.infrastructure.persistence.job_repository import (
    SqlAlchemyJobRepository,
)
from anime_downloader.infrastructure.persistence.library_repository import (
    SqlAlchemyLibraryRepository,
)
from anime_downloader.infrastructure.worker import DownloadWorker


class _TitledAdapter:
    @property
    def adapter_id(self) -> str:
        return "titled"

    def matches(self, url: SourceUrl) -> bool:
        return url.host == "titled.local"

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        _ = url
        return SeasonDiscovery(
            series_title="Frieren",
            season_number=1,
            episodes=(
                EpisodeRef(
                    source_url="https://titled.local/frieren/1/e/1",
                    number=1,
                    title="Journey's End",
                ),
                EpisodeRef(
                    source_url="https://titled.local/frieren/1/e/2",
                    number=2,
                    title="A Mage's Trick",
                ),
            ),
        )

    def resolve_media(self, episode: EpisodeRef) -> MediaLocator:
        return MediaLocator(
            url=f"https://titled.local/media/{episode.number}.mkv",
            suggested_filename=f"ep-{episode.number}.mkv",
        )

    def next_episode(self, episode: EpisodeRef) -> EpisodeRef | None:
        _ = episode
        return None


class _HellsParadiseAdapter:
    @property
    def adapter_id(self) -> str:
        return "hells"

    def matches(self, url: SourceUrl) -> bool:
        return url.host == "hells.local"

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        _ = url
        return SeasonDiscovery(
            series_title="Hell's Paradise",
            season_number=1,
            release_year=2023,
            episodes=(
                EpisodeRef(
                    source_url="https://hells.local/season/hells-paradise/1/e/1",
                    number=1,
                    title="The First Death",
                ),
            ),
        )

    def resolve_media(self, episode: EpisodeRef) -> MediaLocator:
        _ = episode
        return MediaLocator(
            url="https://hells.local/media/1.mp4",
            suggested_filename="episode.mp4",
        )

    def next_episode(self, episode: EpisodeRef) -> EpisodeRef | None:
        _ = episode
        return None


class _BrokenDiscoveryAdapter:
    @property
    def adapter_id(self) -> str:
        return "broken"

    def matches(self, url: SourceUrl) -> bool:
        return url.host == "broken.local"

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        raise RuntimeError(f"upstream 503 for {url.value}")

    def resolve_media(self, episode: EpisodeRef) -> MediaLocator:
        _ = episode
        raise RuntimeError("unreachable")

    def next_episode(self, episode: EpisodeRef) -> EpisodeRef | None:
        _ = episode
        return None


@pytest.fixture
def env(tmp_path: Path):
    db_path = tmp_path / "app.db"
    library_root = tmp_path / "library"
    run_migrations(str(db_path))
    engine = create_engine_for_path(str(db_path))
    session_factory = make_session_factory(engine)
    jobs = SqlAlchemyJobRepository(session_factory)
    library = SqlAlchemyLibraryRepository(session_factory)
    try:
        yield jobs, library, library_root
    finally:
        engine.dispose()


def test_worker_downloads_three_episodes_to_disk_and_updates_db(env) -> None:
    jobs, library, library_root = env
    registry = AdapterRegistry([DemoAdapter(episode_count=3)])
    ids = UuidIdGenerator()
    sleeps: list[float] = []

    job = start_season_download(
        url="https://demo.local/season/demo-show/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )

    worker = DownloadWorker(
        jobs=jobs,
        library=library,
        registry=registry,
        downloader=FakeMediaDownloader(payload=b"demo-video-bytes"),
        library_root=library_root,
        sleep=sleeps.append,
    )
    worker.start_background()
    try:
        worker.enqueue(job.id)
        assert worker.wait_idle(timeout=5.0)
    finally:
        worker.stop()

    assert sleeps == []

    saved_job = jobs.get(job.id)
    assert saved_job is not None
    assert saved_job.status == JobStatus.COMPLETED
    assert saved_job.total_episodes == 3
    assert saved_job.completed_episodes == 3
    assert saved_job.failed_episodes == 0
    assert saved_job.error_message is None

    assert job.season_id is not None
    episodes = library.list_episodes(job.season_id)
    assert len(episodes) == 3

    for n, ep in enumerate(episodes, start=1):
        expected_path = (
            library_root
            / "demo-show (Unknown)"
            / "Season 01"
            / f"demo-show S01E{n:02d}.mp4"
        ).resolve()
        assert ep.status == EpisodeStatus.COMPLETED
        assert ep.error_message is None
        assert ep.file_path == str(expected_path)
        assert expected_path.is_file()
        assert expected_path.read_bytes() == b"demo-video-bytes"


def test_worker_writes_jellyfin_path_ignoring_episode_title(env) -> None:
    jobs, library, library_root = env
    registry = AdapterRegistry([_HellsParadiseAdapter()])
    ids = UuidIdGenerator()

    job = start_season_download(
        url="https://hells.local/season/hells-paradise/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )

    worker = DownloadWorker(
        jobs=jobs,
        library=library,
        registry=registry,
        downloader=FakeMediaDownloader(payload=b"hells-bytes"),
        library_root=library_root,
        sleep=lambda _: None,
    )
    worker.start_background()
    try:
        worker.enqueue(job.id)
        assert worker.wait_idle(timeout=5.0)
    finally:
        worker.stop()

    expected = (
        library_root
        / "Hell's Paradise (2023)"
        / "Season 01"
        / "Hell's Paradise S01E01.mp4"
    )
    assert expected.is_file()
    assert expected.read_bytes() == b"hells-bytes"
    assert job.season_id is not None
    episodes = library.list_episodes(job.season_id)
    assert episodes[0].title == "The First Death"
    assert episodes[0].file_path == str(expected.resolve())


def test_worker_transitions_through_running_and_downloading(
    env,
) -> None:
    jobs, library, library_root = env
    registry = AdapterRegistry([_TitledAdapter()])
    ids = UuidIdGenerator()
    observed_states: list[tuple[int, JobStatus, EpisodeStatus]] = []

    job = start_season_download(
        url="https://titled.local/frieren/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )
    assert job.season_id is not None
    season_id = job.season_id

    class ObservingDownloader:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            current_job = jobs.get(job.id)
            assert current_job is not None
            eps = library.list_episodes(season_id)
            ep_num = 1 if media.url.endswith("/1.mkv") else 2
            ep = next(e for e in eps if e.number == ep_num)
            observed_states.append((ep_num, current_job.status, ep.status))
            return FakeMediaDownloader().download(media, destination)

    worker = DownloadWorker(
        jobs=jobs,
        library=library,
        registry=registry,
        downloader=ObservingDownloader(),
        library_root=library_root,
        sleep=lambda _: None,
    )
    worker.start_background()
    try:
        worker.enqueue(job.id)
        assert worker.wait_idle(timeout=5.0)
    finally:
        worker.stop()

    assert observed_states == [
        (1, JobStatus.RUNNING, EpisodeStatus.DOWNLOADING),
        (2, JobStatus.RUNNING, EpisodeStatus.DOWNLOADING),
    ]

    ep1_path = (
        library_root / "Frieren (Unknown)" / "Season 01" / "Frieren S01E01.mkv"
    ).resolve()
    ep2_path = (
        library_root / "Frieren (Unknown)" / "Season 01" / "Frieren S01E02.mkv"
    ).resolve()
    assert ep1_path.is_file()
    assert ep2_path.is_file()


def test_worker_retries_transient_failure_with_injectable_sleep_backoff(env) -> None:
    jobs, library, library_root = env
    registry = AdapterRegistry([DemoAdapter(episode_count=2)])
    ids = UuidIdGenerator()
    sleeps: list[float] = []
    attempts_by_url: dict[str, int] = {}

    job = start_season_download(
        url="https://demo.local/season/retry-show/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )

    class FlakyDownloader:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            count = attempts_by_url.get(media.url, 0) + 1
            attempts_by_url[media.url] = count
            if media.url.endswith("/1.mp4") and count < 3:
                raise TimeoutError(f"transient failure #{count}")
            return FakeMediaDownloader().download(media, destination)

    worker = DownloadWorker(
        jobs=jobs,
        library=library,
        registry=registry,
        downloader=FlakyDownloader(),
        library_root=library_root,
        sleep=sleeps.append,
    )
    worker.start_background()
    try:
        worker.enqueue(job.id)
        assert worker.wait_idle(timeout=5.0)
    finally:
        worker.stop()

    assert attempts_by_url == {
        "https://demo.local/media/1.mp4": 3,
        "https://demo.local/media/2.mp4": 1,
    }
    assert sleeps == [0.1, 0.2]

    saved_job = jobs.get(job.id)
    assert saved_job is not None
    assert saved_job.status == JobStatus.COMPLETED
    assert saved_job.completed_episodes == 2
    assert saved_job.failed_episodes == 0


def test_worker_marks_episode_failed_after_max_attempts_and_completes_partial_job(
    env,
) -> None:
    jobs, library, library_root = env
    registry = AdapterRegistry([DemoAdapter(episode_count=3)])
    ids = UuidIdGenerator()
    sleeps: list[float] = []
    ep2_attempts = 0

    job = start_season_download(
        url="https://demo.local/season/partial-show/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )

    class Ep2AlwaysFailsDownloader:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            nonlocal ep2_attempts
            if media.url.endswith("/2.mp4"):
                ep2_attempts += 1
                raise ConnectionError("cdn 502 bad gateway")
            return FakeMediaDownloader().download(media, destination)

    worker = DownloadWorker(
        jobs=jobs,
        library=library,
        registry=registry,
        downloader=Ep2AlwaysFailsDownloader(),
        library_root=library_root,
        sleep=sleeps.append,
    )
    worker.start_background()
    try:
        worker.enqueue(job.id)
        assert worker.wait_idle(timeout=5.0)
    finally:
        worker.stop()

    assert ep2_attempts == 3
    assert sleeps == [0.1, 0.2]

    saved_job = jobs.get(job.id)
    assert saved_job is not None
    assert saved_job.status == JobStatus.COMPLETED
    assert saved_job.total_episodes == 3
    assert saved_job.completed_episodes == 2
    assert saved_job.failed_episodes == 1

    assert job.season_id is not None
    eps = library.list_episodes(job.season_id)
    assert eps[0].status == EpisodeStatus.COMPLETED
    assert eps[1].status == EpisodeStatus.FAILED
    assert eps[1].file_path is None
    assert eps[1].error_message is not None
    assert "502" in eps[1].error_message
    assert eps[2].status == EpisodeStatus.COMPLETED


def test_worker_marks_job_failed_when_all_episodes_fail_or_discovery_dies(env) -> None:
    jobs, library, library_root = env
    registry = AdapterRegistry([DemoAdapter(episode_count=2), _BrokenDiscoveryAdapter()])
    ids = UuidIdGenerator()
    sleeps: list[float] = []

    all_fail_job = start_season_download(
        url="https://demo.local/season/doomed-show/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )
    discovery_fail_job = jobs.save(
        DownloadJob(
            id=ids.new_id(),
            source_url="https://broken.local/season/anything/1",
            adapter_id="broken",
            status=JobStatus.PENDING,
        )
    )

    class AlwaysFailsDownloader:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            _ = media, destination
            raise OSError("disk unreachable")

    worker = DownloadWorker(
        jobs=jobs,
        library=library,
        registry=registry,
        downloader=AlwaysFailsDownloader(),
        library_root=library_root,
        sleep=sleeps.append,
        ids=ids,
    )
    worker.start_background()
    try:
        worker.enqueue(all_fail_job.id)
        worker.enqueue(discovery_fail_job.id)
        assert worker.wait_idle(timeout=5.0)
    finally:
        worker.stop()

    assert sleeps == [0.1, 0.2, 0.1, 0.2]

    saved_all_fail = jobs.get(all_fail_job.id)
    assert saved_all_fail is not None
    assert saved_all_fail.status == JobStatus.FAILED
    assert saved_all_fail.completed_episodes == 0
    assert saved_all_fail.failed_episodes == 2
    assert saved_all_fail.error_message is not None

    saved_discovery_fail = jobs.get(discovery_fail_job.id)
    assert saved_discovery_fail is not None
    assert saved_discovery_fail.status == JobStatus.FAILED
    assert saved_discovery_fail.error_message is not None
    assert "503" in saved_discovery_fail.error_message


def test_worker_resume_incomplete_resumes_interrupted_jobs_and_skips_completed(
    env,
) -> None:
    jobs, library, library_root = env
    registry = AdapterRegistry([DemoAdapter(episode_count=3)])
    ids = UuidIdGenerator()
    downloaded_urls: list[str] = []

    crashed_job = start_season_download(
        url="https://demo.local/season/crashed-show/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )
    assert crashed_job.season_id is not None
    eps = library.list_episodes(crashed_job.season_id)

    ep1_existing_path = (
        library_root / "crashed-show" / "1" / "S01E01 - Episode 1.mp4"
    ).resolve()
    ep1_existing_path.parent.mkdir(parents=True, exist_ok=True)
    ep1_existing_path.write_bytes(b"already-downloaded")

    library.upsert_episode(
        Episode(
            id=eps[0].id,
            season_id=crashed_job.season_id,
            number=1,
            title=eps[0].title,
            status=EpisodeStatus.COMPLETED,
            source_url=eps[0].source_url,
            file_path=str(ep1_existing_path),
        )
    )
    library.upsert_episode(
        Episode(
            id=eps[1].id,
            season_id=crashed_job.season_id,
            number=2,
            title=eps[1].title,
            status=EpisodeStatus.DOWNLOADING,
            source_url=eps[1].source_url,
        )
    )
    jobs.save(
        DownloadJob(
            id=crashed_job.id,
            source_url=crashed_job.source_url,
            adapter_id=crashed_job.adapter_id,
            status=JobStatus.RUNNING,
            series_id=crashed_job.series_id,
            season_id=crashed_job.season_id,
            total_episodes=3,
            completed_episodes=1,
            failed_episodes=0,
        )
    )

    finished_job = jobs.save(
        DownloadJob(
            id=ids.new_id(),
            source_url="https://demo.local/season/old-show/1",
            adapter_id="demo",
            status=JobStatus.COMPLETED,
            total_episodes=3,
            completed_episodes=3,
        )
    )

    class RecordingDownloader:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            downloaded_urls.append(media.url)
            return FakeMediaDownloader(payload=b"fresh-bytes").download(
                media, destination
            )

    worker = DownloadWorker(
        jobs=jobs,
        library=library,
        registry=registry,
        downloader=RecordingDownloader(),
        library_root=library_root,
        sleep=lambda _: None,
    )
    worker.resume_incomplete()
    worker.start_background()
    try:
        assert worker.wait_idle(timeout=5.0)
    finally:
        worker.stop()

    assert downloaded_urls == [
        "https://demo.local/media/2.mp4",
        "https://demo.local/media/3.mp4",
    ]
    assert ep1_existing_path.read_bytes() == b"already-downloaded"

    resumed_job = jobs.get(crashed_job.id)
    assert resumed_job is not None
    assert resumed_job.status == JobStatus.COMPLETED
    assert resumed_job.completed_episodes == 3
    assert resumed_job.failed_episodes == 0

    untouched_finished = jobs.get(finished_job.id)
    assert untouched_finished is not None
    assert untouched_finished.status == JobStatus.COMPLETED


def test_worker_integrates_with_retry_failed_use_case(env) -> None:
    jobs, library, library_root = env
    registry = AdapterRegistry([DemoAdapter(episode_count=2)])
    ids = UuidIdGenerator()
    fail_ep2 = True

    initial_job = start_season_download(
        url="https://demo.local/season/recover-show/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )
    assert initial_job.season_id is not None

    class ToggleDownloader:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            if fail_ep2 and media.url.endswith("/2.mp4"):
                raise ConnectionError("temporary outage")
            return FakeMediaDownloader().download(media, destination)

    worker = DownloadWorker(
        jobs=jobs,
        library=library,
        registry=registry,
        downloader=ToggleDownloader(),
        library_root=library_root,
        sleep=lambda _: None,
    )
    worker.start_background()
    try:
        worker.enqueue(initial_job.id)
        assert worker.wait_idle(timeout=5.0)

        first_after = jobs.get(initial_job.id)
        assert first_after is not None
        assert first_after.completed_episodes == 1
        assert first_after.failed_episodes == 1

        fail_ep2 = False
        retried_job = retry_failed(
            season_id=initial_job.season_id,
            library=library,
            jobs=jobs,
            ids=ids,
        )
        worker.enqueue(retried_job.id)
        assert worker.wait_idle(timeout=5.0)
    finally:
        worker.stop()

    final_retry = jobs.get(retried_job.id)
    assert final_retry is not None
    assert final_retry.status == JobStatus.COMPLETED
    assert final_retry.completed_episodes == 2
    assert final_retry.failed_episodes == 0


def test_worker_marks_retry_job_failed_when_zero_retried_episodes_succeed(
    env,
) -> None:
    jobs, library, library_root = env
    registry = AdapterRegistry([DemoAdapter(episode_count=2)])
    ids = UuidIdGenerator()

    initial_job = start_season_download(
        url="https://demo.local/season/still-broken/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )
    assert initial_job.season_id is not None

    class Ep2BrokenDownloader:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            if media.url.endswith("/2.mp4"):
                raise ConnectionError("still down")
            return FakeMediaDownloader().download(media, destination)

    worker = DownloadWorker(
        jobs=jobs,
        library=library,
        registry=registry,
        downloader=Ep2BrokenDownloader(),
        library_root=library_root,
        sleep=lambda _: None,
    )
    worker.start_background()
    try:
        worker.enqueue(initial_job.id)
        assert worker.wait_idle(timeout=5.0)

        retried_job = retry_failed(
            season_id=initial_job.season_id,
            library=library,
            jobs=jobs,
            ids=ids,
        )
        worker.enqueue(retried_job.id)
        assert worker.wait_idle(timeout=5.0)
    finally:
        worker.stop()

    final_retry = jobs.get(retried_job.id)
    assert final_retry is not None
    assert final_retry.status == JobStatus.FAILED
    assert final_retry.completed_episodes == 1
    assert final_retry.failed_episodes == 1
    assert final_retry.error_message is not None
    assert "still down" in final_retry.error_message


def test_worker_skips_already_completed_episodes(env) -> None:
    jobs, library, library_root = env
    ids = UuidIdGenerator()
    registry = AdapterRegistry([DemoAdapter(episode_count=2)])

    series = library.upsert_series(Series(id=ids.new_id(), title="demo-show"))
    season = library.upsert_season(
        Season(id=ids.new_id(), series_id=series.id, number=1)
    )
    for n in (1, 2):
        path = library_root / "demo-show" / "1" / f"S01E{n:02d} - Episode {n}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"already-there")
        library.upsert_episode(
            Episode(
                id=ids.new_id(),
                season_id=season.id,
                number=n,
                title=f"Episode {n}",
                status=EpisodeStatus.COMPLETED,
                source_url=f"https://demo.local/season/demo-show/1/e/{n}",
                file_path=str(path.resolve()),
                error_message=None,
            )
        )

    download_calls: list[str] = []

    class RecordingDownloader:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            download_calls.append(media.url)
            raise AssertionError("should not download completed episodes")

    worker = DownloadWorker(
        jobs=jobs,
        library=library,
        registry=registry,
        downloader=RecordingDownloader(),
        library_root=library_root,
        sleep=lambda _: None,
        ids=ids,
    )
    job = start_season_download(
        url="https://demo.local/season/demo-show/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )
    # Point job at existing series/season so hierarchy resume path is exercised
    jobs.save(
        DownloadJob(
            id=job.id,
            source_url=job.source_url,
            adapter_id=job.adapter_id,
            status=job.status,
            series_id=series.id,
            season_id=season.id,
            total_episodes=2,
            completed_episodes=2,
            failed_episodes=0,
            error_message=None,
        )
    )
    worker.start_background()
    try:
        worker.enqueue(job.id)
        assert worker.wait_idle(timeout=5.0)
    finally:
        worker.stop()

    assert download_calls == []
    refreshed = jobs.get(job.id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.COMPLETED
    assert (
        library_root / "demo-show" / "1" / "S01E01 - Episode 1.mp4"
    ).read_bytes() == b"already-there"


def test_worker_module_has_top_level_imports_only() -> None:
    worker_file = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "anime_downloader"
        / "infrastructure"
        / "worker.py"
    )
    tree = ast.parse(worker_file.read_text(encoding="utf-8"), filename=str(worker_file))
    top_level_imports = {
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert node in top_level_imports, "Inline import found in worker.py"
