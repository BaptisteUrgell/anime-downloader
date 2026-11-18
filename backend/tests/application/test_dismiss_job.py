from __future__ import annotations

from pathlib import Path

import pytest

from anime_downloader.application.dismiss_job import dismiss_completed_jobs, dismiss_job
from anime_downloader.application.get_job import list_jobs
from anime_downloader.domain.errors import JobCannotBeDismissed, JobNotFound
from anime_downloader.domain.model import DownloadJob, JobStatus
from anime_downloader.infrastructure.db.session import (
    create_engine_for_path,
    make_session_factory,
    run_migrations,
)
from anime_downloader.infrastructure.persistence.job_repository import (
    SqlAlchemyJobRepository,
)


class FixedClock:
    def __init__(self, value: str = "2026-11-18T12:00:00+00:00") -> None:
        self.value = value

    def now_iso(self) -> str:
        return self.value


def _repo(tmp_path: Path) -> SqlAlchemyJobRepository:
    db = tmp_path / "app.db"
    engine = create_engine_for_path(db)
    run_migrations(db)
    return SqlAlchemyJobRepository(make_session_factory(engine))


def _job(**kwargs) -> DownloadJob:
    base = dict(
        id="job-1",
        source_url="https://demo.local/season/show/1",
        adapter_id="demo",
        status=JobStatus.COMPLETED,
        total_episodes=3,
        completed_episodes=3,
    )
    base.update(kwargs)
    return DownloadJob(**base)


def test_dismiss_job_sets_dismissed_at(tmp_path: Path) -> None:
    jobs = _repo(tmp_path)
    jobs.save(_job())
    clock = FixedClock()

    out = dismiss_job("job-1", jobs, clock)

    assert out.dismissed_at == clock.value
    assert list_jobs(jobs) == []
    assert jobs.get("job-1") is not None
    assert jobs.get("job-1").dismissed_at == clock.value


def test_dismiss_job_rejects_active(tmp_path: Path) -> None:
    jobs = _repo(tmp_path)
    jobs.save(_job(status=JobStatus.RUNNING, completed_episodes=1))

    with pytest.raises(JobCannotBeDismissed):
        dismiss_job("job-1", jobs, FixedClock())


def test_dismiss_job_missing_raises(tmp_path: Path) -> None:
    jobs = _repo(tmp_path)
    with pytest.raises(JobNotFound):
        dismiss_job("missing", jobs, FixedClock())


def test_dismiss_completed_skips_failed_and_active(tmp_path: Path) -> None:
    jobs = _repo(tmp_path)
    jobs.save(_job(id="done", status=JobStatus.COMPLETED))
    jobs.save(_job(id="fail", status=JobStatus.FAILED, failed_episodes=1, completed_episodes=2))
    jobs.save(_job(id="run", status=JobStatus.RUNNING, completed_episodes=0))

    count = dismiss_completed_jobs(jobs, FixedClock())

    assert count == 1
    visible = {j.id for j in list_jobs(jobs)}
    assert visible == {"fail", "run"}