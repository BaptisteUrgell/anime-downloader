from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from anime_downloader.domain.model import (
    Episode,
    EpisodeRef,
    EpisodeStatus,
    Season,
    SeasonDiscovery,
    Series,
    SourceUrl,
)
from anime_downloader.infrastructure.adapter_registry import AdapterRegistry
from anime_downloader.infrastructure.db.models import EpisodeRow, SeasonRow, SeriesRow
from anime_downloader.infrastructure.db.session import (
    create_engine_for_path,
    make_session_factory,
    run_migrations,
)
from anime_downloader.infrastructure.library_migrator import migrate_library
from anime_downloader.infrastructure.library_paths import build_episode_path
from anime_downloader.infrastructure.persistence.library_repository import (
    SqlAlchemyLibraryRepository,
)


class _MetaAdapter:
    def __init__(self, *, season_number: int = 1) -> None:
        self._season_number = season_number

    @property
    def adapter_id(self) -> str:
        return "stub"

    def matches(self, url: SourceUrl) -> bool:
        return url.host == "stub.local"

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        return SeasonDiscovery(
            series_title="Hell's Paradise",
            release_year=2023,
            season_number=self._season_number,
            episodes=(EpisodeRef(source_url=url.value, number=1),),
        )


@pytest.fixture
def session_factory(tmp_path: Path):
    db_path = tmp_path / "app.db"
    run_migrations(str(db_path))
    engine = create_engine_for_path(str(db_path))
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


def _repo(session_factory) -> SqlAlchemyLibraryRepository:
    return SqlAlchemyLibraryRepository(session_factory)


def _completed_episode(
    repo: SqlAlchemyLibraryRepository,
    *,
    series_id: str,
    title: str,
    season_id: str,
    episode_id: str,
    number: int,
    source_url: str,
    file_path: Path,
    payload: bytes,
    season_number: int = 1,
) -> None:
    repo.upsert_series(Series(id=series_id, title=title, release_year=None))
    repo.upsert_season(
        Season(id=season_id, series_id=series_id, number=season_number)
    )
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(payload)
    repo.upsert_episode(
        Episode(
            id=episode_id,
            season_id=season_id,
            number=number,
            title="Episode",
            status=EpisodeStatus.COMPLETED,
            source_url=source_url,
            file_path=str(file_path),
        )
    )


def test_migrates_old_slug_layout_to_jellyfin(tmp_path: Path, session_factory) -> None:
    library_root = tmp_path / "library"
    repo = _repo(session_factory)
    old_path = (
        library_root / "hells-paradise-vostfr" / "1" / "S01E01 - hells-paradise-vostfr.mp4"
    )
    _completed_episode(
        repo,
        series_id="s-vostfr",
        title="hells-paradise-vostfr",
        season_id="sea-1",
        episode_id="ep-1",
        number=1,
        source_url="https://stub.local/catalogue/hells-paradise/saison1/vostfr",
        file_path=old_path,
        payload=b"episode-bytes",
    )

    report = migrate_library(
        library=repo,
        registry=AdapterRegistry([_MetaAdapter(season_number=9)]),
        library_root=library_root,
    )

    expected = build_episode_path(
        library_root,
        "Hell's Paradise",
        2023,
        season_number=1,
        episode_number=1,
        ext="mp4",
    )
    assert expected.is_file()
    assert expected.read_bytes() == b"episode-bytes"
    assert not old_path.exists()
    assert not (library_root / "hells-paradise-vostfr").exists()
    stored = repo.get_episode("ep-1")
    assert stored is not None
    assert Path(stored.file_path or "") == expected
    series = repo.list_series()
    assert series == [Series(id="s-vostfr", title="Hell's Paradise", release_year=2023)]
    assert report.renamed_files == 1
    assert report.merged_series == 0
    assert report.errors == []


def test_migrate_is_idempotent(tmp_path: Path, session_factory) -> None:
    library_root = tmp_path / "library"
    repo = _repo(session_factory)
    old_path = (
        library_root / "hells-paradise-vostfr" / "1" / "S01E01 - hells-paradise-vostfr.mp4"
    )
    _completed_episode(
        repo,
        series_id="s-vostfr",
        title="hells-paradise-vostfr",
        season_id="sea-1",
        episode_id="ep-1",
        number=1,
        source_url="https://stub.local/catalogue/hells-paradise/saison1/vostfr",
        file_path=old_path,
        payload=b"episode-bytes",
    )
    registry = AdapterRegistry([_MetaAdapter()])

    first = migrate_library(library=repo, registry=registry, library_root=library_root)
    expected = build_episode_path(
        library_root, "Hell's Paradise", 2023, 1, 1, "mp4"
    )
    second = migrate_library(library=repo, registry=registry, library_root=library_root)

    assert first.renamed_files == 1
    assert second.renamed_files == 0
    assert second.merged_series == 0
    assert second.errors == []
    assert expected.read_bytes() == b"episode-bytes"
    assert repo.list_series() == [
        Series(id="s-vostfr", title="Hell's Paradise", release_year=2023)
    ]


def test_merge_duplicate_series_same_title_year(tmp_path: Path, session_factory) -> None:
    library_root = tmp_path / "library"
    repo = _repo(session_factory)
    vf_path = library_root / "hells-paradise-vf" / "1" / "S01E01 - hells-paradise-vf.mp4"
    vostfr_path = (
        library_root
        / "hells-paradise-vostfr"
        / "1"
        / "S01E01 - hells-paradise-vostfr.mp4"
    )
    _completed_episode(
        repo,
        series_id="s-vf",
        title="hells-paradise-vf",
        season_id="sea-vf",
        episode_id="ep-vf",
        number=1,
        source_url="https://stub.local/catalogue/hells-paradise/saison1/vf",
        file_path=vf_path,
        payload=b"vf-bytes",
    )
    _completed_episode(
        repo,
        series_id="s-vostfr",
        title="hells-paradise-vostfr",
        season_id="sea-vostfr",
        episode_id="ep-vostfr",
        number=1,
        source_url="https://stub.local/catalogue/hells-paradise/saison1/vostfr",
        file_path=vostfr_path,
        payload=b"vostfr-bytes-longer",
    )

    report = migrate_library(
        library=repo,
        registry=AdapterRegistry([_MetaAdapter()]),
        library_root=library_root,
    )

    expected = build_episode_path(
        library_root, "Hell's Paradise", 2023, 1, 1, "mp4"
    )
    assert expected.read_bytes() == b"vf-bytes"
    assert not vf_path.exists()
    assert not vostfr_path.exists()
    assert report.merged_series == 1
    assert report.errors == []
    series = repo.list_series()
    assert len(series) == 1
    assert series[0].title == "Hell's Paradise"
    assert series[0].release_year == 2023
    seasons = repo.list_seasons(series[0].id)
    assert [season.number for season in seasons] == [1]
    episodes = repo.list_episodes(seasons[0].id)
    assert len(episodes) == 1
    assert Path(episodes[0].file_path or "") == expected
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SeriesRow)) == 1
        assert session.scalar(select(func.count()).select_from(SeasonRow)) == 1
        assert session.scalar(select(func.count()).select_from(EpisodeRow)) == 1


def test_same_season_merge_keeps_completed_file_when_earlier_row_failed(
    tmp_path: Path, session_factory
) -> None:
    library_root = tmp_path / "library"
    repo = _repo(session_factory)
    payload = b"completed-episode-bytes"
    completed_path = (
        library_root / "zzz-hells-paradise" / "1" / "S01E01 - zzz-hells-paradise.mp4"
    )
    repo.upsert_series(Series(id="s-failed", title="Hell's Paradise", release_year=2023))
    repo.upsert_season(Season(id="sea-failed", series_id="s-failed", number=1))
    repo.upsert_episode(
        Episode(
            id="ep-failed",
            season_id="sea-failed",
            number=1,
            title="Episode",
            status=EpisodeStatus.FAILED,
            source_url="https://stub.local/catalogue/hells-paradise/saison1/vf",
            error_message="download failed",
        )
    )
    _completed_episode(
        repo,
        series_id="s-done",
        title="zzz-hells-paradise",
        season_id="sea-done",
        episode_id="ep-done",
        number=1,
        source_url="https://stub.local/catalogue/hells-paradise/saison1/vostfr",
        file_path=completed_path,
        payload=payload,
    )
    assert [series.id for series in repo.list_series()] == ["s-failed", "s-done"]
    registry = AdapterRegistry([_MetaAdapter()])

    migrate_library(library=repo, registry=registry, library_root=library_root)
    expected = build_episode_path(library_root, "Hell's Paradise", 2023, 1, 1, "mp4")
    second = migrate_library(library=repo, registry=registry, library_root=library_root)

    assert expected.is_file()
    assert expected.read_bytes() == payload
    survivor = repo.get_episode("ep-failed")
    assert survivor is not None
    assert survivor.status == EpisodeStatus.COMPLETED
    assert survivor.error_message is None
    assert Path(survivor.file_path or "") == expected
    assert Path(survivor.file_path or "").read_bytes() == payload
    assert repo.get_episode("ep-done") is None
    assert second.errors == []
    assert expected.read_bytes() == payload


def test_same_season_merge_keeps_duplicate_when_files_differ(
    tmp_path: Path, session_factory
) -> None:
    library_root = tmp_path / "library"
    repo = _repo(session_factory)
    vf_path = library_root / "hells-paradise-vf" / "1" / "S01E01 - hells-paradise-vf.mp4"
    vostfr_path = (
        library_root
        / "hells-paradise-vostfr"
        / "1"
        / "S01E01 - hells-paradise-vostfr.mkv"
    )
    _completed_episode(
        repo,
        series_id="s-vf",
        title="hells-paradise-vf",
        season_id="sea-vf",
        episode_id="ep-vf",
        number=1,
        source_url="https://stub.local/catalogue/hells-paradise/saison1/vf",
        file_path=vf_path,
        payload=b"vf-bytes",
    )
    _completed_episode(
        repo,
        series_id="s-vostfr",
        title="hells-paradise-vostfr",
        season_id="sea-vostfr",
        episode_id="ep-vostfr",
        number=1,
        source_url="https://stub.local/catalogue/hells-paradise/saison1/vostfr",
        file_path=vostfr_path,
        payload=b"vostfr-bytes",
    )
    registry = AdapterRegistry([_MetaAdapter()])

    report = migrate_library(library=repo, registry=registry, library_root=library_root)
    mp4_path = build_episode_path(library_root, "Hell's Paradise", 2023, 1, 1, "mp4")
    mkv_path = build_episode_path(library_root, "Hell's Paradise", 2023, 1, 1, "mkv")
    second = migrate_library(library=repo, registry=registry, library_root=library_root)

    assert report.merged_series == 0
    assert any("different files" in error for error in report.errors)
    assert any("different files" in error for error in second.errors)
    assert {series.id for series in repo.list_series()} == {"s-vf", "s-vostfr"}
    kept_vf = repo.get_episode("ep-vf")
    kept_vostfr = repo.get_episode("ep-vostfr")
    assert kept_vf is not None and kept_vostfr is not None
    assert Path(kept_vf.file_path or "") == mp4_path
    assert Path(kept_vostfr.file_path or "") == mkv_path
    assert mp4_path.read_bytes() == b"vf-bytes"
    assert mkv_path.read_bytes() == b"vostfr-bytes"


def test_reassigns_distinct_season_onto_canonical_series(
    tmp_path: Path, session_factory
) -> None:
    library_root = tmp_path / "library"
    repo = _repo(session_factory)
    vf_path = library_root / "hells-paradise-vf" / "1" / "S01E01 - hells-paradise-vf.mp4"
    vostfr_path = (
        library_root / "hells-paradise-vostfr" / "2" / "S02E01 - hells-paradise-vostfr.mp4"
    )
    _completed_episode(
        repo,
        series_id="s-vf",
        title="hells-paradise-vf",
        season_id="sea-vf",
        episode_id="ep-vf",
        number=1,
        source_url="https://stub.local/catalogue/hells-paradise/saison1/vf",
        file_path=vf_path,
        payload=b"season-one",
    )
    _completed_episode(
        repo,
        series_id="s-vostfr",
        title="hells-paradise-vostfr",
        season_id="sea-vostfr",
        episode_id="ep-vostfr",
        number=1,
        source_url="https://stub.local/catalogue/hells-paradise/saison2/vostfr",
        file_path=vostfr_path,
        payload=b"season-two",
        season_number=2,
    )

    report = migrate_library(
        library=repo,
        registry=AdapterRegistry([_MetaAdapter()]),
        library_root=library_root,
    )

    series = repo.list_series()
    assert len(series) == 1
    assert report.merged_series == 1
    assert [season.number for season in repo.list_seasons(series[0].id)] == [1, 2]
    season_one = build_episode_path(library_root, "Hell's Paradise", 2023, 1, 1, "mp4")
    season_two = build_episode_path(library_root, "Hell's Paradise", 2023, 2, 1, "mp4")
    assert season_one.read_bytes() == b"season-one"
    assert season_two.read_bytes() == b"season-two"


def test_discovery_failure_is_cached_for_the_same_url(
    tmp_path: Path, session_factory
) -> None:
    library_root = tmp_path / "library"
    repo = _repo(session_factory)
    source_url = "https://stub.local/catalogue/hells-paradise/saison1/vostfr"

    class _OfflineAdapter:
        def __init__(self) -> None:
            self.calls = 0

        @property
        def adapter_id(self) -> str:
            return "stub"

        def matches(self, url: SourceUrl) -> bool:
            return url.host == "stub.local"

        def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
            self.calls += 1
            raise RuntimeError(f"offline {url.value}")

    for number in (1, 2):
        _completed_episode(
            repo,
            series_id="s-vostfr",
            title="hells-paradise-vostfr",
            season_id="sea-1",
            episode_id=f"ep-{number}",
            number=number,
            source_url=source_url,
            file_path=library_root / "hells-paradise-vostfr" / "1" / f"E{number}.mp4",
            payload=b"pending-migrate",
        )
    adapter = _OfflineAdapter()

    report = migrate_library(
        library=repo,
        registry=AdapterRegistry([adapter]),
        library_root=library_root,
    )

    assert adapter.calls == 1
    assert len(report.errors) == 2
    assert repo.list_series() == [
        Series(id="s-vostfr", title="hells-paradise-vostfr", release_year=None)
    ]


def test_skips_unknown_host_and_leaves_file(tmp_path: Path, session_factory, caplog) -> None:
    library_root = tmp_path / "library"
    repo = _repo(session_factory)
    old_path = library_root / "demo-show" / "1" / "S01E01 - demo-show.mp4"
    source_url = "https://demo.local/watch/1"
    _completed_episode(
        repo,
        series_id="s-demo",
        title="demo-show",
        season_id="sea-demo",
        episode_id="ep-demo",
        number=1,
        source_url=source_url,
        file_path=old_path,
        payload=b"demo-bytes",
    )

    with caplog.at_level("WARNING"):
        report = migrate_library(
            library=repo,
            registry=AdapterRegistry([_MetaAdapter()]),
            library_root=library_root,
        )

    assert old_path.read_bytes() == b"demo-bytes"
    assert repo.list_series() == [Series(id="s-demo", title="demo-show", release_year=None)]
    assert report.renamed_files == 0
    assert report.merged_series == 0
    assert any("demo.local" in error for error in report.errors)
    assert any("demo.local" in record.message for record in caplog.records)
