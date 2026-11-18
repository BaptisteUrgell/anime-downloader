from typing import Annotated

from fastapi import APIRouter, Depends, status

from anime_downloader.api.deps import (
    get_clock,
    get_id_generator,
    get_job_repository,
    get_library_repository,
    get_registry,
    get_worker,
)
from anime_downloader.api.schemas import (
    CreateJobRequest,
    DismissCompletedResponse,
    EpisodePreviewResponse,
    ErrorResponse,
    JobResponse,
    PreviewJobRequest,
    RetryFailedRequest,
    SeasonPreviewResponse,
)
from anime_downloader.application.dismiss_job import (
    dismiss_completed_jobs,
    dismiss_job,
)
from anime_downloader.application.get_job import get_job, list_jobs
from anime_downloader.application.preview_season import preview_season
from anime_downloader.application.retry_failed import retry_failed
from anime_downloader.application.start_season_download import start_season_download
from anime_downloader.domain.ports import (
    AdapterRegistry,
    Clock,
    IdGenerator,
    JobRepository,
    LibraryRepository,
)
from anime_downloader.domain.model import DownloadJob
from anime_downloader.infrastructure.worker import DownloadWorker

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_response(job: DownloadJob, worker: DownloadWorker | None = None) -> JobResponse:
    response = JobResponse.model_validate(job)
    if worker is None:
        return response
    progress = worker.get_download_progress(job.id)
    if progress is None:
        return response
    return response.model_copy(
        update={
            "current_episode_number": progress.episode_number,
            "episode_progress_percent": progress.percent,
        }
    )


@router.post(
    "/preview",
    response_model=SeasonPreviewResponse,
    operation_id="previewSeason",
    responses={
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def preview_season_endpoint(
    body: PreviewJobRequest,
    registry: Annotated[AdapterRegistry, Depends(get_registry)],
) -> SeasonPreviewResponse:
    discovery = preview_season(body.url, registry)
    return SeasonPreviewResponse(
        series_title=discovery.series_title,
        season_number=discovery.season_number,
        episode_count=discovery.episode_count,
        episodes=[
            EpisodePreviewResponse.model_validate(ep) for ep in discovery.episodes
        ],
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=JobResponse,
    operation_id="createJob",
    responses={
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def create_job_endpoint(
    body: CreateJobRequest,
    registry: Annotated[AdapterRegistry, Depends(get_registry)],
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    library: Annotated[LibraryRepository, Depends(get_library_repository)],
    ids: Annotated[IdGenerator, Depends(get_id_generator)],
    worker: Annotated[DownloadWorker, Depends(get_worker)],
) -> JobResponse:
    job = start_season_download(
        url=body.url,
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )
    response = _job_response(job, worker)
    worker.enqueue(job.id)
    return response


@router.get(
    "",
    response_model=list[JobResponse],
    operation_id="listJobs",
)
def list_jobs_endpoint(
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    worker: Annotated[DownloadWorker, Depends(get_worker)],
) -> list[JobResponse]:
    return [_job_response(job, worker) for job in list_jobs(jobs)]


@router.post(
    "/retry-failed",
    response_model=JobResponse,
    operation_id="retryFailedEpisodes",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def retry_failed_endpoint(
    body: RetryFailedRequest,
    library: Annotated[LibraryRepository, Depends(get_library_repository)],
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    ids: Annotated[IdGenerator, Depends(get_id_generator)],
    worker: Annotated[DownloadWorker, Depends(get_worker)],
) -> JobResponse:
    job = retry_failed(
        season_id=body.season_id,
        library=library,
        jobs=jobs,
        ids=ids,
    )
    response = _job_response(job, worker)
    worker.enqueue(job.id)
    return response


@router.post(
    "/dismiss-completed",
    response_model=DismissCompletedResponse,
    operation_id="dismissCompletedJobs",
)
def dismiss_completed_endpoint(
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> DismissCompletedResponse:
    return DismissCompletedResponse(
        dismissed_count=dismiss_completed_jobs(jobs, clock)
    )


@router.post(
    "/{id}/dismiss",
    response_model=JobResponse,
    operation_id="dismissJob",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def dismiss_job_endpoint(
    id: str,
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    clock: Annotated[Clock, Depends(get_clock)],
    worker: Annotated[DownloadWorker, Depends(get_worker)],
) -> JobResponse:
    job = dismiss_job(id, jobs, clock)
    return _job_response(job, worker)


@router.get(
    "/{id}",
    response_model=JobResponse,
    operation_id="getJob",
    responses={
        404: {"model": ErrorResponse},
    },
)
def get_job_endpoint(
    id: str,
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    worker: Annotated[DownloadWorker, Depends(get_worker)],
) -> JobResponse:
    job = get_job(id, jobs)
    return _job_response(job, worker)
