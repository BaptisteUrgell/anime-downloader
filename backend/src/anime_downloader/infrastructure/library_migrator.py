from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from anime_downloader.domain.errors import InvalidSourceUrl, NoAdapterFound
from anime_downloader.domain.model import (
    Episode,
    EpisodeStatus,
    SeasonDiscovery,
    Series,
    SourceUrl,
)
from anime_downloader.domain.ports import (
    AdapterRegistry,
    LibraryRepository,
    SourceAdapter,
)
from anime_downloader.infrastructure.library_paths import build_episode_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationReport:
    renamed_files: int
    merged_series: int
    errors: list[str]


@dataclass(frozen=True)
class _MovePlan:
    old_path: Path
    new_path: Path


@dataclass
class _DiscoveryCache:
    found: dict[tuple[str, str], SeasonDiscovery]
    failed: dict[tuple[str, str], Exception]


def migrate_library(
    *,
    library: LibraryRepository,
    registry: AdapterRegistry,
    library_root: Path,
) -> MigrationReport:
    renamed_files = 0
    merged_series = 0
    errors: list[str] = []
    discovery_cache = _DiscoveryCache(found={}, failed={})

    for series in library.list_series():
        identity: SeasonDiscovery | None = None
        for season in library.list_seasons(series.id):
            for episode in library.list_episodes(season.id):
                if episode.status != EpisodeStatus.COMPLETED or not episode.file_path:
                    continue
                discovery, renamed = _migrate_episode(
                    library=library,
                    registry=registry,
                    library_root=library_root,
                    season_number=season.number,
                    episode=episode,
                    discovery_cache=discovery_cache,
                    errors=errors,
                )
                if discovery is None:
                    continue
                if renamed:
                    renamed_files += 1
                if identity is None:
                    identity = discovery
                elif not _same_identity(identity, discovery):
                    _record(
                        errors,
                        (
                            f"Series {series.id} episodes resolved to multiple titles; "
                            f"keeping {identity.series_title!r} ({identity.release_year})"
                        ),
                    )
        if identity is None:
            continue
        try:
            if _merge_series_if_needed(library, series, identity):
                merged_series += 1
        except Exception as exc:
            _record(errors, f"Failed to update series {series.id}: {exc}")

    _prune_empty_dirs(library_root)
    return MigrationReport(
        renamed_files=renamed_files,
        merged_series=merged_series,
        errors=errors,
    )


def _migrate_episode(
    *,
    library: LibraryRepository,
    registry: AdapterRegistry,
    library_root: Path,
    season_number: int,
    episode: Episode,
    discovery_cache: _DiscoveryCache,
    errors: list[str],
) -> tuple[SeasonDiscovery | None, bool]:
    try:
        source_url = SourceUrl.parse(episode.source_url)
        adapter = registry.resolve(source_url)
    except (InvalidSourceUrl, NoAdapterFound) as exc:
        _record(errors, f"Skipping episode {episode.id}: {exc}")
        return None, False

    try:
        discovery = _discover(adapter, source_url, discovery_cache)
        plan = _plan_move(episode, library_root, discovery, season_number)
        renamed = _apply_move(plan)
    except Exception as exc:
        _record(errors, f"Skipping episode {episode.id}: {exc}")
        return None, False

    library.upsert_episode(
        Episode(
            id=episode.id,
            season_id=episode.season_id,
            number=episode.number,
            title=episode.title,
            status=episode.status,
            source_url=episode.source_url,
            file_path=str(plan.new_path),
            error_message=episode.error_message,
        )
    )
    return discovery, renamed


def _plan_move(
    episode: Episode,
    library_root: Path,
    discovery: SeasonDiscovery,
    season_number: int,
) -> _MovePlan:
    old_path = Path(episode.file_path or "")
    new_path = build_episode_path(
        library_root,
        discovery.series_title,
        discovery.release_year,
        season_number,
        episode.number,
        old_path.suffix.lstrip("."),
    )
    return _MovePlan(old_path=old_path, new_path=new_path)


def _apply_move(plan: _MovePlan) -> bool:
    if plan.old_path.resolve() == plan.new_path.resolve():
        return False
    if not plan.old_path.is_file():
        if plan.new_path.is_file():
            return False
        raise FileNotFoundError(f"Missing library file: {plan.old_path}")

    plan.new_path.parent.mkdir(parents=True, exist_ok=True)
    if not plan.new_path.exists():
        plan.old_path.replace(plan.new_path)
        return True
    if not plan.new_path.is_file():
        raise FileExistsError(f"Target is not a file: {plan.new_path}")

    old_size = plan.old_path.stat().st_size
    new_size = plan.new_path.stat().st_size
    if old_size != new_size:
        logger.warning(
            "Keeping existing %s (%s bytes); removing %s (%s bytes)",
            plan.new_path,
            new_size,
            plan.old_path,
            old_size,
        )
    plan.old_path.unlink()
    return True


def _merge_series_if_needed(
    library: LibraryRepository,
    series: Series,
    discovery: SeasonDiscovery,
) -> bool:
    canonical = _canonical_series(library, series.id, discovery)
    if canonical is None:
        library.upsert_series(
            Series(
                id=series.id,
                title=discovery.series_title,
                release_year=discovery.release_year,
            )
        )
        return False

    for season in library.list_seasons(series.id):
        target = next(
            (
                item
                for item in library.list_seasons(canonical.id)
                if item.number == season.number
            ),
            None,
        )
        if target is None:
            library.reassign_season(season.id, canonical.id)
            continue
        occupied = {episode.number for episode in library.list_episodes(target.id)}
        for episode in library.list_episodes(season.id):
            if episode.number in occupied:
                continue
            library.upsert_episode(
                Episode(
                    id=episode.id,
                    season_id=target.id,
                    number=episode.number,
                    title=episode.title,
                    status=episode.status,
                    source_url=episode.source_url,
                    file_path=episode.file_path,
                    error_message=episode.error_message,
                )
            )
            occupied.add(episode.number)
        library.delete_season(season.id)

    if library.list_seasons(series.id):
        return False
    library.delete_series(series.id)
    return True


def _canonical_series(
    library: LibraryRepository,
    series_id: str,
    discovery: SeasonDiscovery,
) -> Series | None:
    for existing in library.list_series():
        if existing.id == series_id:
            continue
        if (
            existing.title == discovery.series_title
            and existing.release_year == discovery.release_year
        ):
            return existing
    return None


def _discover(
    adapter: SourceAdapter,
    url: SourceUrl,
    cache: _DiscoveryCache,
) -> SeasonDiscovery:
    key = (adapter.adapter_id, url.value)
    failure = cache.failed.get(key)
    if failure is not None:
        raise failure
    cached = cache.found.get(key)
    if cached is not None:
        return cached
    try:
        discovered = adapter.discover_season(url)
    except Exception as exc:
        cache.failed[key] = exc
        raise
    cache.found[key] = discovered
    return discovered


def _same_identity(left: SeasonDiscovery, right: SeasonDiscovery) -> bool:
    return (
        left.series_title == right.series_title
        and left.release_year == right.release_year
    )


def _prune_empty_dirs(library_root: Path) -> None:
    if not library_root.is_dir():
        return
    directories = sorted(
        (path for path in library_root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        except OSError as exc:
            logger.warning("Could not remove empty directory %s: %s", directory, exc)


def _record(errors: list[str], message: str) -> None:
    logger.warning("%s", message)
    errors.append(message)
