from __future__ import annotations

from anime_downloader.domain.errors import JobCannotBeDismissed, JobNotFound
from anime_downloader.domain.model import DownloadJob, JobStatus
from anime_downloader.domain.ports import Clock, JobRepository

_ACTIVE = {JobStatus.PENDING, JobStatus.RUNNING}


def dismiss_job(job_id: str, jobs: JobRepository, clock: Clock) -> DownloadJob:
    job = jobs.get(job_id)
    if job is None:
        raise JobNotFound(f"Job not found: {job_id}")
    if job.status in _ACTIVE:
        raise JobCannotBeDismissed(
            f"Cannot dismiss job in status {job.status.value}: {job_id}"
        )
    if job.dismissed_at is not None:
        return job
    job.dismissed_at = clock.now_iso()
    return jobs.save(job)


def dismiss_completed_jobs(jobs: JobRepository, clock: Clock) -> int:
    count = 0
    for job in jobs.list_jobs():
        if job.dismissed_at is not None:
            continue
        if job.status != JobStatus.COMPLETED:
            continue
        job.dismissed_at = clock.now_iso()
        jobs.save(job)
        count += 1
    return count