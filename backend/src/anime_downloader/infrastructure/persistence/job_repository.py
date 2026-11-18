from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from anime_downloader.domain.model import DownloadJob, JobStatus
from anime_downloader.infrastructure.db.models import JobRow


class SqlAlchemyJobRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(self, job: DownloadJob) -> DownloadJob:
        with self._session_factory() as session:
            row = session.get(JobRow, job.id)
            if row is not None:
                row.source_url = job.source_url
                row.adapter_id = job.adapter_id
                row.status = job.status.value
                row.series_id = job.series_id
                row.season_id = job.season_id
                row.total_episodes = job.total_episodes
                row.completed_episodes = job.completed_episodes
                row.failed_episodes = job.failed_episodes
                row.error_message = job.error_message
                row.dismissed_at = job.dismissed_at
            else:
                row = JobRow(
                    id=job.id,
                    source_url=job.source_url,
                    adapter_id=job.adapter_id,
                    status=job.status.value,
                    series_id=job.series_id,
                    season_id=job.season_id,
                    total_episodes=job.total_episodes,
                    completed_episodes=job.completed_episodes,
                    failed_episodes=job.failed_episodes,
                    error_message=job.error_message,
                    dismissed_at=job.dismissed_at,
                )
                session.add(row)
            session.commit()
            return _to_job(row)

    def get(self, job_id: str) -> DownloadJob | None:
        with self._session_factory() as session:
            row = session.get(JobRow, job_id)
            return _to_job(row) if row is not None else None

    def list_jobs(self) -> list[DownloadJob]:
        with self._session_factory() as session:
            rows = session.scalars(select(JobRow)).all()
            return [_to_job(row) for row in rows]

    def list_resumable(self) -> list[DownloadJob]:
        resumable_statuses = (JobStatus.PENDING.value, JobStatus.RUNNING.value)
        with self._session_factory() as session:
            rows = session.scalars(
                select(JobRow).where(JobRow.status.in_(resumable_statuses))
            ).all()
            return [_to_job(row) for row in rows]


def _to_job(row: JobRow) -> DownloadJob:
    return DownloadJob(
        id=row.id,
        source_url=row.source_url,
        adapter_id=row.adapter_id,
        status=JobStatus(row.status),
        series_id=row.series_id,
        season_id=row.season_id,
        total_episodes=row.total_episodes,
        completed_episodes=row.completed_episodes,
        failed_episodes=row.failed_episodes,
        error_message=row.error_message,
        dismissed_at=row.dismissed_at,
    )
