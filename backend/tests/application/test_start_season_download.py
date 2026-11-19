from __future__ import annotations

import ast
from pathlib import Path

import pytest

from anime_downloader.application.get_job import get_job, list_jobs
from anime_downloader.application.list_library import (
    LibrarySeason,
    LibrarySeries,
    list_library,
)
from anime_downloader.application.preview_season import preview_season
from anime_downloader.application.retry_failed import retry_failed
from anime_downloader.application.start_season_download import start_season_download
from anime_downloader.domain.errors import (
    DiscoveryFailed,
    InvalidSourceUrl,
    JobNotFound,
    NoAdapterFound,
    NoFailedEpisodes,
    SeasonNotFound,
)
from anime_downloader.domain.model import (
    DownloadJob,
    Episode,
    EpisodeRef,
    EpisodeStatus,
    JobStatus,
    MediaLocator,
    SeasonDiscovery,
    SourceUrl,
)
from anime_downloader.infrastructure.adapter_registry import AdapterRegistry
from anime_downloader.infrastructure.db.session import (
    create_engine_for_path,
    make_session_factory,
    run_migrations,
)
from tests.support.fake_season_adapter import FakeSeasonAdapter
from anime_downloader.infrastructure.ids import UuidIdGenerator
from anime_downloader.infrastructure.persistence.job_repository import (
    SqlAlchemyJobRepository,
)
from anime_downloader.infrastructure.persistence.library_repository import (
    SqlAlchemyLibraryRepository,
)


class _YearAdapter:
    @property
    def adapter_id(self) -> str:
        return "year-stub"

    def matches(self, url: SourceUrl) -> bool:
        return url.host == "year.local"

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        return SeasonDiscovery(
            series_title="Hell's Paradise",
            season_number=1,
            release_year=2023,
            episodes=(
                EpisodeRef(source_url=url.value + "/e/1", number=1),
            ),
        )

    def resolve_media(self, episode: EpisodeRef) -> MediaLocator:
        return MediaLocator(url="https://year.local/media/1.mp4")

    def next_episode(self, episode: EpisodeRef) -> EpisodeRef | None:
        return None


class _MutableEpisodeAdapter:
    def __init__(self, episode_count: int) -> None:
        self.episode_count = episode_count
        self.discover_calls = 0

    @property
    def adapter_id(self) -> str:
        return "mutable"

    def matches(self, url: SourceUrl) -> bool:
        return url.host == "mutable.local"

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        self.discover_calls += 1
        episodes = tuple(
            EpisodeRef(
                source_url=f"https://mutable.local/season/live-show/1/e/{n}",
                number=n,
                title=f"Episode {n}",
            )
            for n in range(1, self.episode_count + 1)
        )
        return SeasonDiscovery(
            series_title="live-show",
            season_number=1,
            episodes=episodes,
        )

    def resolve_media(self, episode: EpisodeRef) -> MediaLocator:
        return MediaLocator(url=f"https://mutable.local/media/{episode.number}.mp4")

    def next_episode(self, episode: EpisodeRef) -> EpisodeRef | None:
        return None


@pytest.fixture
def repos(tmp_path: Path):
    db_path = tmp_path / "app.db"
    run_migrations(str(db_path))
    engine = create_engine_for_path(str(db_path))
    session_factory = make_session_factory(engine)
    try:
        yield (
            SqlAlchemyJobRepository(session_factory),
            SqlAlchemyLibraryRepository(session_factory),
        )
    finally:
        engine.dispose()


def test_start_season_download_stores_release_year(repos) -> None:
    jobs, library = repos
    registry = AdapterRegistry([_YearAdapter()])
    ids = UuidIdGenerator()

    start_season_download(
        url="https://year.local/season/hells-paradise/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )

    series_list = library.list_series()
    assert len(series_list) == 1
    assert series_list[0].title == "Hell's Paradise"
    assert series_list[0].release_year == 2023


def test_start_season_download_creates_and_persists_hierarchy_and_pending_job(
    repos,
) -> None:
    jobs, library = repos
    registry = AdapterRegistry([FakeSeasonAdapter(episode_count=3)])
    ids = UuidIdGenerator()

    job = start_season_download(
        url="https://fake.local/season/frieren/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )

    assert job.status == JobStatus.PENDING
    assert job.adapter_id == "fake"
    assert job.source_url == "https://fake.local/season/frieren/1"
    assert job.total_episodes == 3
    assert job.completed_episodes == 0
    assert job.failed_episodes == 0
    assert job.series_id is not None
    assert job.season_id is not None
    assert job.error_message is None

    persisted_job = get_job(job.id, jobs)
    assert persisted_job == job
    assert list_jobs(jobs) == [job]

    series_list = library.list_series()
    assert len(series_list) == 1
    assert series_list[0].id == job.series_id
    assert series_list[0].title == "frieren"
    assert series_list[0].release_year == 2020

    seasons = library.list_seasons(job.series_id)
    assert len(seasons) == 1
    assert seasons[0].id == job.season_id
    assert seasons[0].number == 1

    episodes = library.list_episodes(job.season_id)
    assert [ep.number for ep in episodes] == [1, 2, 3]
    assert all(ep.status == EpisodeStatus.PENDING for ep in episodes)
    assert [ep.source_url for ep in episodes] == [
        "https://fake.local/season/frieren/1/e/1",
        "https://fake.local/season/frieren/1/e/2",
        "https://fake.local/season/frieren/1/e/3",
    ]


def test_start_season_download_rediscovers_instead_of_trusting_cached_preview(
    repos,
) -> None:
    jobs, library = repos
    adapter = _MutableEpisodeAdapter(episode_count=2)
    registry = AdapterRegistry([adapter])
    ids = UuidIdGenerator()
    url = "https://mutable.local/season/live-show/1"

    preview = preview_season(url, registry)
    assert preview.episode_count == 2
    assert adapter.discover_calls == 1

    adapter.episode_count = 4
    job = start_season_download(url, registry, jobs, library, ids)

    assert adapter.discover_calls == 2
    assert job.total_episodes == 4
    assert job.season_id is not None
    episodes = library.list_episodes(job.season_id)
    assert [ep.number for ep in episodes] == [1, 2, 3, 4]
    assert all(ep.status == EpisodeStatus.PENDING for ep in episodes)


def test_start_season_download_preserves_completed_episodes_on_redownload(
    repos,
) -> None:
    jobs, library = repos
    registry = AdapterRegistry([FakeSeasonAdapter(episode_count=3)])
    ids = UuidIdGenerator()
    url = "https://fake.local/season/orb/1"

    first_job = start_season_download(url, registry, jobs, library, ids)
    assert first_job.season_id is not None
    initial_eps = library.list_episodes(first_job.season_id)

    library.upsert_episode(
        Episode(
            id=initial_eps[0].id,
            season_id=first_job.season_id,
            number=1,
            title="Ep 1",
            status=EpisodeStatus.COMPLETED,
            source_url=initial_eps[0].source_url,
            file_path="/data/library/orb/1/E01.mp4",
        )
    )
    library.upsert_episode(
        Episode(
            id=initial_eps[1].id,
            season_id=first_job.season_id,
            number=2,
            title="Ep 2",
            status=EpisodeStatus.FAILED,
            source_url=initial_eps[1].source_url,
            error_message="network timeout",
        )
    )

    second_job = start_season_download(url, registry, jobs, library, ids)

    assert second_job.id != first_job.id
    assert second_job.series_id == first_job.series_id
    assert second_job.season_id == first_job.season_id
    assert second_job.status == JobStatus.PENDING
    assert second_job.total_episodes == 3
    assert second_job.completed_episodes == 1
    assert second_job.failed_episodes == 0

    refreshed_eps = library.list_episodes(first_job.season_id)
    assert len(refreshed_eps) == 3
    assert refreshed_eps[0].status == EpisodeStatus.COMPLETED
    assert refreshed_eps[0].file_path == "/data/library/orb/1/E01.mp4"
    assert refreshed_eps[1].status == EpisodeStatus.PENDING
    assert refreshed_eps[1].error_message is None
    assert refreshed_eps[2].status == EpisodeStatus.PENDING


def test_start_season_download_validates_url_adapter_and_discovery_errors(
    repos,
) -> None:
    jobs, library = repos
    registry = AdapterRegistry([FakeSeasonAdapter(episode_count=3)])
    ids = UuidIdGenerator()

    with pytest.raises(InvalidSourceUrl):
        start_season_download("bad-url", registry, jobs, library, ids)

    with pytest.raises(NoAdapterFound):
        start_season_download(
            "https://unknown.local/season/show/1", registry, jobs, library, ids
        )

    with pytest.raises(DiscoveryFailed):
        start_season_download(
            "https://fake.local/season/missing-season-num",
            registry,
            jobs,
            library,
            ids,
        )

    assert jobs.list_jobs() == []
    assert library.list_series() == []


def test_get_job_raises_job_not_found_for_unknown_id(repos) -> None:
    jobs, _ = repos

    with pytest.raises(JobNotFound):
        get_job("non-existent-job", jobs)


def test_list_library_returns_nested_series_seasons_and_episodes(repos) -> None:
    jobs, library = repos
    registry = AdapterRegistry([FakeSeasonAdapter(episode_count=2)])
    ids = UuidIdGenerator()

    assert list_library(library) == []

    job_b = start_season_download(
        "https://fake.local/season/vinland/2", registry, jobs, library, ids
    )
    job_a1 = start_season_download(
        "https://fake.local/season/frieren/1", registry, jobs, library, ids
    )
    assert job_a1.season_id is not None
    assert job_b.season_id is not None

    frieren_eps = library.list_episodes(job_a1.season_id)
    library.upsert_episode(
        Episode(
            id=frieren_eps[0].id,
            season_id=job_a1.season_id,
            number=1,
            title="Journey's End",
            status=EpisodeStatus.COMPLETED,
            source_url=frieren_eps[0].source_url,
            file_path="/data/library/frieren/1/E01 - Journey's End.mp4",
        )
    )

    tree = list_library(library)

    assert len(tree) == 2
    assert all(isinstance(node, LibrarySeries) for node in tree)
    assert [node.title for node in tree] == ["frieren", "vinland"]

    frieren_node = tree[0]
    assert len(frieren_node.seasons) == 1
    assert isinstance(frieren_node.seasons[0], LibrarySeason)
    assert frieren_node.seasons[0].number == 1
    assert len(frieren_node.seasons[0].episodes) == 2
    assert frieren_node.seasons[0].episodes[0].status == EpisodeStatus.COMPLETED
    assert (
        frieren_node.seasons[0].episodes[0].file_path
        == "/data/library/frieren/1/E01 - Journey's End.mp4"
    )
    assert frieren_node.seasons[0].episodes[1].status == EpisodeStatus.PENDING


def test_retry_failed_resets_failed_episodes_and_enqueues_pending_job(repos) -> None:
    jobs, library = repos
    registry = AdapterRegistry([FakeSeasonAdapter(episode_count=3)])
    ids = UuidIdGenerator()

    initial_job = start_season_download(
        "https://fake.local/season/meshi/1", registry, jobs, library, ids
    )
    assert initial_job.season_id is not None
    eps = library.list_episodes(initial_job.season_id)

    library.upsert_episode(
        Episode(
            id=eps[0].id,
            season_id=initial_job.season_id,
            number=1,
            title=eps[0].title,
            status=EpisodeStatus.COMPLETED,
            source_url=eps[0].source_url,
            file_path="/data/library/meshi/1/E01.mp4",
        )
    )
    for failed_ep in eps[1:]:
        library.upsert_episode(
            Episode(
                id=failed_ep.id,
                season_id=initial_job.season_id,
                number=failed_ep.number,
                title=failed_ep.title,
                status=EpisodeStatus.FAILED,
                source_url=failed_ep.source_url,
                error_message="connection reset",
            )
        )
    jobs.save(
        DownloadJob(
            id=initial_job.id,
            source_url=initial_job.source_url,
            adapter_id=initial_job.adapter_id,
            status=JobStatus.FAILED,
            series_id=initial_job.series_id,
            season_id=initial_job.season_id,
            total_episodes=3,
            completed_episodes=1,
            failed_episodes=2,
            error_message="2 episodes failed",
        )
    )

    retried_job = retry_failed(
        season_id=initial_job.season_id,
        library=library,
        jobs=jobs,
        ids=ids,
    )

    assert retried_job.id != initial_job.id
    assert retried_job.status == JobStatus.PENDING
    assert retried_job.source_url == "https://fake.local/season/meshi/1"
    assert retried_job.adapter_id == "fake"
    assert retried_job.series_id == initial_job.series_id
    assert retried_job.season_id == initial_job.season_id
    assert retried_job.total_episodes == 3
    assert retried_job.completed_episodes == 1
    assert retried_job.failed_episodes == 0
    assert retried_job.error_message is None

    assert get_job(retried_job.id, jobs) == retried_job
    assert [j.id for j in jobs.list_resumable()] == [retried_job.id]

    assert library.list_failed_episodes(initial_job.season_id) == []
    updated_eps = library.list_episodes(initial_job.season_id)
    assert updated_eps[0].status == EpisodeStatus.COMPLETED
    assert updated_eps[0].file_path == "/data/library/meshi/1/E01.mp4"
    assert updated_eps[1].status == EpisodeStatus.PENDING
    assert updated_eps[1].error_message is None
    assert updated_eps[2].status == EpisodeStatus.PENDING
    assert updated_eps[2].error_message is None


def test_retry_failed_raises_for_unknown_season_or_no_failed_episodes(repos) -> None:
    jobs, library = repos
    registry = AdapterRegistry([FakeSeasonAdapter(episode_count=2)])
    ids = UuidIdGenerator()

    with pytest.raises(SeasonNotFound):
        retry_failed("unknown-season-id", library, jobs, ids)

    job = start_season_download(
        "https://fake.local/season/clean-show/1", registry, jobs, library, ids
    )
    assert job.season_id is not None

    with pytest.raises(NoFailedEpisodes):
        retry_failed(job.season_id, library, jobs, ids)


def test_application_layer_depends_only_on_domain_and_top_level_imports() -> None:
    app_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "anime_downloader"
        / "application"
    )
    py_files = sorted(app_dir.glob("*.py"))
    assert len(py_files) >= 6

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        top_level_imports = {
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                assert node in top_level_imports, (
                    f"Inline import found in {py_file.name}"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("anime_downloader"):
                        assert alias.name.startswith(
                            ("anime_downloader.domain", "anime_downloader.application")
                        ), f"Forbidden import {alias.name} in {py_file.name}"
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("anime_downloader"):
                    assert node.module.startswith(
                        ("anime_downloader.domain", "anime_downloader.application")
                    ), f"Forbidden import {node.module} in {py_file.name}"
