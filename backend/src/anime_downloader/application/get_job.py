from __future__ import annotations

from anime_downloader.domain.errors import JobNotFound
from anime_downloader.domain.model import DownloadJob
from anime_downloader.domain.ports import JobRepository


def get_job(job_id: str, jobs: JobRepository) -> DownloadJob:
    job = jobs.get(job_id)
    if job is None:
        raise JobNotFound(f"Job not found: {job_id}")
    return job


def list_jobs(jobs: JobRepository) -> list[DownloadJob]:
    return jobs.list_jobs()
