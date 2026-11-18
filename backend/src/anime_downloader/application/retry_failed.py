from __future__ import annotations

from anime_downloader.domain.errors import NoFailedEpisodes, SeasonNotFound
from anime_downloader.domain.model import (
    DownloadJob,
    Episode,
    EpisodeStatus,
    JobStatus,
    Season,
)
from anime_downloader.domain.ports import (
    IdGenerator,
    JobRepository,
    LibraryRepository,
)


def retry_failed(
    season_id: str,
    library: LibraryRepository,
    jobs: JobRepository,
    ids: IdGenerator,
) -> DownloadJob:
    season = _find_season(season_id, library)
    if season is None:
        raise SeasonNotFound(f"Season not found: {season_id}")

    failed_episodes = library.list_failed_episodes(season_id)
    if not failed_episodes:
        raise NoFailedEpisodes(f"No failed episodes for season: {season_id}")

    for ep in failed_episodes:
        library.upsert_episode(
            Episode(
                id=ep.id,
                season_id=ep.season_id,
                number=ep.number,
                title=ep.title,
                status=EpisodeStatus.PENDING,
                source_url=ep.source_url,
                file_path=None,
                error_message=None,
            )
        )

    all_episodes = library.list_episodes(season_id)
    completed_count = sum(
        1 for ep in all_episodes if ep.status == EpisodeStatus.COMPLETED
    )

    prior_job = _find_latest_job_for_season(season_id, jobs)
    source_url = (
        prior_job.source_url
        if prior_job is not None
        else failed_episodes[0].source_url
    )
    adapter_id = prior_job.adapter_id if prior_job is not None else "unknown"

    job = DownloadJob(
        id=ids.new_id(),
        source_url=source_url,
        adapter_id=adapter_id,
        status=JobStatus.PENDING,
        series_id=season.series_id,
        season_id=season.id,
        total_episodes=len(all_episodes),
        completed_episodes=completed_count,
        failed_episodes=0,
        error_message=None,
    )
    return jobs.save(job)


def _find_season(season_id: str, library: LibraryRepository) -> Season | None:
    for series in library.list_series():
        for season in library.list_seasons(series.id):
            if season.id == season_id:
                return season
    return None


def _find_latest_job_for_season(
    season_id: str, jobs: JobRepository
) -> DownloadJob | None:
    matching = [job for job in jobs.list_jobs() if job.season_id == season_id]
    return matching[-1] if matching else None
