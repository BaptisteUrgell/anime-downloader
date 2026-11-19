from __future__ import annotations

from anime_downloader.domain.errors import DiscoveryFailed, DomainError
from anime_downloader.domain.model import (
    DownloadJob,
    Episode,
    EpisodeStatus,
    JobStatus,
    Season,
    Series,
    SourceUrl,
)
from anime_downloader.domain.ports import (
    AdapterRegistry,
    IdGenerator,
    JobRepository,
    LibraryRepository,
)


def start_season_download(
    url: str,
    registry: AdapterRegistry,
    jobs: JobRepository,
    library: LibraryRepository,
    ids: IdGenerator,
) -> DownloadJob:
    source_url = SourceUrl.parse(url)
    adapter = registry.resolve(source_url)
    try:
        discovery = adapter.discover_season(source_url)
    except DomainError:
        raise
    except Exception as exc:
        raise DiscoveryFailed(
            f"Season discovery failed for {source_url.value}: {exc}"
        ) from exc

    existing_series = next(
        (
            s
            for s in library.list_series()
            if s.title == discovery.series_title
            and s.release_year == discovery.release_year
        ),
        None,
    )
    series_id = existing_series.id if existing_series is not None else ids.new_id()
    series = library.upsert_series(
        Series(
            id=series_id,
            title=discovery.series_title,
            release_year=discovery.release_year,
        )
    )

    existing_season = next(
        (
            s
            for s in library.list_seasons(series.id)
            if s.number == discovery.season_number
        ),
        None,
    )
    season_id = existing_season.id if existing_season is not None else ids.new_id()
    season = library.upsert_season(
        Season(id=season_id, series_id=series.id, number=discovery.season_number)
    )

    existing_episodes_by_number = {
        ep.number: ep for ep in library.list_episodes(season.id)
    }
    persisted_episodes: list[Episode] = []
    for ep_ref in discovery.episodes:
        existing_ep = existing_episodes_by_number.get(ep_ref.number)
        if existing_ep is not None and existing_ep.status == EpisodeStatus.COMPLETED:
            episode = Episode(
                id=existing_ep.id,
                season_id=season.id,
                number=ep_ref.number,
                title=ep_ref.title if ep_ref.title is not None else existing_ep.title,
                status=EpisodeStatus.COMPLETED,
                source_url=ep_ref.source_url,
                file_path=existing_ep.file_path,
                error_message=None,
            )
        else:
            ep_id = existing_ep.id if existing_ep is not None else ids.new_id()
            episode = Episode(
                id=ep_id,
                season_id=season.id,
                number=ep_ref.number,
                title=ep_ref.title,
                status=EpisodeStatus.PENDING,
                source_url=ep_ref.source_url,
                file_path=None,
                error_message=None,
            )
        persisted_episodes.append(library.upsert_episode(episode))

    completed_count = sum(
        1 for ep in persisted_episodes if ep.status == EpisodeStatus.COMPLETED
    )
    job = DownloadJob(
        id=ids.new_id(),
        source_url=source_url.value,
        adapter_id=adapter.adapter_id,
        status=JobStatus.PENDING,
        series_id=series.id,
        season_id=season.id,
        total_episodes=len(persisted_episodes),
        completed_episodes=completed_count,
        failed_episodes=0,
        error_message=None,
    )
    return jobs.save(job)
