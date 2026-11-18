from pydantic import BaseModel, ConfigDict

from anime_downloader.domain.model import EpisodeStatus, JobStatus


class ErrorResponse(BaseModel):
    detail: str


class PreviewJobRequest(BaseModel):
    url: str


class EpisodePreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int
    title: str | None = None


class SeasonPreviewResponse(BaseModel):
    series_title: str
    season_number: int
    episode_count: int
    episodes: list[EpisodePreviewResponse]


class CreateJobRequest(BaseModel):
    url: str


class RetryFailedRequest(BaseModel):
    season_id: str


class DismissCompletedResponse(BaseModel):
    dismissed_count: int


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_url: str
    adapter_id: str
    status: JobStatus
    series_id: str | None = None
    season_id: str | None = None
    total_episodes: int
    completed_episodes: int
    failed_episodes: int
    error_message: str | None = None
    current_episode_number: int | None = None
    episode_progress_percent: float | None = None
    dismissed_at: str | None = None


class EpisodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    season_id: str
    number: int
    title: str | None = None
    status: EpisodeStatus
    source_url: str
    file_path: str | None = None
    error_message: str | None = None


class LibrarySeasonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    series_id: str
    number: int
    episodes: list[EpisodeResponse]


class LibrarySeriesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    seasons: list[LibrarySeasonResponse]
