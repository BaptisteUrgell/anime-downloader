from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from anime_downloader.domain.errors import InvalidSourceUrl


class EpisodeStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class SourceUrl:
    value: str

    @staticmethod
    def parse(raw: str) -> SourceUrl:
        text = (raw or "").strip()
        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise InvalidSourceUrl(f"Invalid source URL: {raw!r}")
        return SourceUrl(value=text)

    def __str__(self) -> str:
        return self.value

    @property
    def host(self) -> str:
        return urlparse(self.value).netloc.lower()


@dataclass(frozen=True)
class EpisodeRef:
    source_url: str
    number: int
    title: str | None = None


@dataclass(frozen=True)
class SeasonDiscovery:
    series_title: str
    season_number: int
    episodes: tuple[EpisodeRef, ...]

    @property
    def episode_count(self) -> int:
        return len(self.episodes)


@dataclass(frozen=True)
class MediaLocator:
    url: str
    suggested_filename: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Series:
    id: str
    title: str


@dataclass
class Season:
    id: str
    series_id: str
    number: int


@dataclass
class Episode:
    id: str
    season_id: str
    number: int
    title: str | None
    status: EpisodeStatus
    source_url: str
    file_path: str | None = None
    error_message: str | None = None


@dataclass
class DownloadJob:
    id: str
    source_url: str
    adapter_id: str
    status: JobStatus
    series_id: str | None = None
    season_id: str | None = None
    total_episodes: int = 0
    completed_episodes: int = 0
    failed_episodes: int = 0
    error_message: str | None = None
    dismissed_at: str | None = None