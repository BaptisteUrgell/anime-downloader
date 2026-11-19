from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import queue
import threading
import time
from urllib.parse import urlparse

from anime_downloader.domain.model import (
    DownloadJob,
    Episode,
    EpisodeRef,
    EpisodeStatus,
    JobStatus,
    MediaLocator,
    Season,
    Series,
    SourceUrl,
)
from anime_downloader.domain.ports import (
    AdapterRegistry,
    IdGenerator,
    JobRepository,
    LibraryRepository,
    MediaDownloader,
    SourceAdapter,
)
from anime_downloader.infrastructure.ids import UuidIdGenerator


@dataclass(frozen=True)
class JobDownloadProgress:
    episode_number: int | None = None
    percent: float | None = None


class DownloadWorker:
    def __init__(
        self,
        jobs: JobRepository,
        library: LibraryRepository,
        registry: AdapterRegistry,
        downloader: MediaDownloader,
        library_root: str | Path,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
        backoff_base: float = 0.1,
        ids: IdGenerator | None = None,
    ) -> None:
        self._jobs = jobs
        self._library = library
        self._registry = registry
        self._downloader = downloader
        self._library_root = Path(library_root)
        self._sleep = sleep
        self._max_attempts = max(1, max_attempts)
        self._backoff_base = backoff_base
        self._ids: IdGenerator = ids if ids is not None else UuidIdGenerator()

        self._queue: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.Lock()
        self._queued_or_active: set[str] = set()
        self._download_progress: dict[str, JobDownloadProgress] = {}
        self._idle_event = threading.Event()
        self._idle_event.set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def get_download_progress(self, job_id: str) -> JobDownloadProgress | None:
        with self._lock:
            progress = self._download_progress.get(job_id)
            return None if progress is None else JobDownloadProgress(
                episode_number=progress.episode_number,
                percent=progress.percent,
            )

    def _set_download_progress(
        self,
        job_id: str,
        *,
        episode_number: int | None,
        percent: float | None,
    ) -> None:
        with self._lock:
            self._download_progress[job_id] = JobDownloadProgress(
                episode_number=episode_number,
                percent=percent,
            )

    def _clear_download_progress(self, job_id: str) -> None:
        with self._lock:
            self._download_progress.pop(job_id, None)

    def enqueue(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._queued_or_active:
                return
            self._queued_or_active.add(job_id)
            self._idle_event.clear()
            self._queue.put(job_id)

    def start_background(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="anime-downloader-worker",
                daemon=True,
            )
            self._thread.start()

    def resume_incomplete(self) -> None:
        resumable = self._jobs.list_resumable()
        for job in resumable:
            if job.season_id is not None:
                for ep in self._library.list_episodes(job.season_id):
                    if ep.status == EpisodeStatus.DOWNLOADING:
                        self._library.upsert_episode(
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
            self.enqueue(job.id)

    def wait_idle(self, timeout: float = 5.0) -> bool:
        return self._idle_event.wait(timeout=timeout)

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                return
            self._stop_event.set()
            self._queue.put(None)
        thread.join(timeout=timeout)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            try:
                self._process_job(item)
            finally:
                self._clear_download_progress(item)
                with self._lock:
                    self._queued_or_active.discard(item)
                    if not self._queued_or_active:
                        self._idle_event.set()
                self._queue.task_done()

    def _process_job(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None or job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
            return

        initial_status = job.status
        job = self._jobs.save(
            DownloadJob(
                id=job.id,
                source_url=job.source_url,
                adapter_id=job.adapter_id,
                status=JobStatus.RUNNING,
                series_id=job.series_id,
                season_id=job.season_id,
                total_episodes=job.total_episodes,
                completed_episodes=job.completed_episodes,
                failed_episodes=job.failed_episodes,
                error_message=None,
            )
        )

        try:
            source_url = SourceUrl.parse(job.source_url)
            adapter = self._registry.resolve(source_url)
            series, season, episodes, job = self._ensure_season_hierarchy(
                job, source_url, adapter
            )
        except Exception as exc:
            self._fail_job(job, str(exc) or exc.__class__.__name__)
            return

        if not episodes:
            self._fail_job(job, "Season discovery returned zero episodes")
            return

        processed_count = 0
        succeeded_in_run = 0
        last_failure_error: str | None = None
        for episode in episodes:
            if episode.status not in {
                EpisodeStatus.PENDING,
                EpisodeStatus.DOWNLOADING,
            }:
                continue

            processed_count += 1
            error = self._download_episode_with_retries(
                job_id=job.id,
                episode=episode,
                series=series,
                season=season,
                adapter=adapter,
            )
            if error is None:
                succeeded_in_run += 1
            else:
                last_failure_error = error

            job = self._save_job_progress(job, season.id, status=JobStatus.RUNNING)

        final_episodes = self._library.list_episodes(season.id)
        completed_count = sum(
            1 for ep in final_episodes if ep.status == EpisodeStatus.COMPLETED
        )
        failed_count = sum(
            1 for ep in final_episodes if ep.status == EpisodeStatus.FAILED
        )
        pending_count = sum(
            1
            for ep in final_episodes
            if ep.status in {EpisodeStatus.PENDING, EpisodeStatus.DOWNLOADING}
        )

        all_attempted_failed_in_new_job = (
            initial_status == JobStatus.PENDING
            and processed_count > 0
            and succeeded_in_run == 0
        )

        if pending_count > 0:
            final_status = JobStatus.RUNNING
            final_error = None
        elif completed_count > 0 and not all_attempted_failed_in_new_job:
            final_status = JobStatus.COMPLETED
            final_error = None
        else:
            final_status = JobStatus.FAILED
            final_error = last_failure_error or "All episodes failed"

        self._jobs.save(
            DownloadJob(
                id=job.id,
                source_url=job.source_url,
                adapter_id=job.adapter_id,
                status=final_status,
                series_id=series.id,
                season_id=season.id,
                total_episodes=len(final_episodes),
                completed_episodes=completed_count,
                failed_episodes=failed_count,
                error_message=final_error,
            )
        )

    def _ensure_season_hierarchy(
        self,
        job: DownloadJob,
        source_url: SourceUrl,
        adapter: SourceAdapter,
    ) -> tuple[Series, Season, list[Episode], DownloadJob]:
        if job.series_id is not None and job.season_id is not None:
            series = next(
                (s for s in self._library.list_series() if s.id == job.series_id),
                None,
            )
            season = (
                next(
                    (
                        s
                        for s in self._library.list_seasons(series.id)
                        if s.id == job.season_id
                    ),
                    None,
                )
                if series is not None
                else None
            )
            if series is not None and season is not None:
                episodes = self._library.list_episodes(season.id)
                if episodes:
                    return series, season, episodes, job

        discovery = adapter.discover_season(source_url)
        existing_series = next(
            (
                s
                for s in self._library.list_series()
                if s.title == discovery.series_title
                and s.release_year == discovery.release_year
            ),
            None,
        )
        series_id = (
            existing_series.id if existing_series is not None else self._ids.new_id()
        )
        series = self._library.upsert_series(
            Series(
                id=series_id,
                title=discovery.series_title,
                release_year=discovery.release_year,
            )
        )

        existing_season = next(
            (
                s
                for s in self._library.list_seasons(series.id)
                if s.number == discovery.season_number
            ),
            None,
        )
        season_id = (
            existing_season.id if existing_season is not None else self._ids.new_id()
        )
        season = self._library.upsert_season(
            Season(id=season_id, series_id=series.id, number=discovery.season_number)
        )

        existing_by_num = {ep.number: ep for ep in self._library.list_episodes(season.id)}
        for ep_ref in discovery.episodes:
            existing_ep = existing_by_num.get(ep_ref.number)
            if existing_ep is not None and existing_ep.status == EpisodeStatus.COMPLETED:
                continue
            ep_id = existing_ep.id if existing_ep is not None else self._ids.new_id()
            self._library.upsert_episode(
                Episode(
                    id=ep_id,
                    season_id=season.id,
                    number=ep_ref.number,
                    title=ep_ref.title,
                    status=EpisodeStatus.PENDING,
                    source_url=ep_ref.source_url,
                    file_path=None,
                    error_message=None,
                )
            )

        episodes = self._library.list_episodes(season.id)
        completed_count = sum(
            1 for ep in episodes if ep.status == EpisodeStatus.COMPLETED
        )
        failed_count = sum(1 for ep in episodes if ep.status == EpisodeStatus.FAILED)
        updated_job = self._jobs.save(
            DownloadJob(
                id=job.id,
                source_url=job.source_url,
                adapter_id=adapter.adapter_id,
                status=JobStatus.RUNNING,
                series_id=series.id,
                season_id=season.id,
                total_episodes=len(episodes),
                completed_episodes=completed_count,
                failed_episodes=failed_count,
                error_message=None,
            )
        )
        return series, season, episodes, updated_job

    def _download_episode_with_retries(
        self,
        job_id: str,
        episode: Episode,
        series: Series,
        season: Season,
        adapter: SourceAdapter,
    ) -> str | None:
        self._set_download_progress(
            job_id, episode_number=episode.number, percent=0.0
        )
        self._library.upsert_episode(
            Episode(
                id=episode.id,
                season_id=episode.season_id,
                number=episode.number,
                title=episode.title,
                status=EpisodeStatus.DOWNLOADING,
                source_url=episode.source_url,
                file_path=None,
                error_message=None,
            )
        )

        ep_ref = EpisodeRef(
            source_url=episode.source_url,
            number=episode.number,
            title=episode.title,
        )
        last_error = "Download failed"
        for attempt in range(1, self._max_attempts + 1):
            try:
                media = adapter.resolve_media(ep_ref)
                destination = self._build_destination_path(
                    series=series,
                    season=season,
                    episode=episode,
                    media=media,
                )

                def on_progress(percent: float, *, _job_id: str = job_id, _n: int = episode.number) -> None:
                    self._set_download_progress(
                        _job_id, episode_number=_n, percent=percent
                    )

                written_path = self._downloader.download(
                    media, str(destination), on_progress=on_progress
                )
                self._set_download_progress(
                    job_id, episode_number=episode.number, percent=100.0
                )
                self._library.upsert_episode(
                    Episode(
                        id=episode.id,
                        season_id=episode.season_id,
                        number=episode.number,
                        title=episode.title,
                        status=EpisodeStatus.COMPLETED,
                        source_url=episode.source_url,
                        file_path=written_path,
                        error_message=None,
                    )
                )
                return None
            except Exception as exc:
                last_error = str(exc) or exc.__class__.__name__
                if attempt < self._max_attempts:
                    self._sleep(round(self._backoff_base * attempt, 10))

        self._library.upsert_episode(
            Episode(
                id=episode.id,
                season_id=episode.season_id,
                number=episode.number,
                title=episode.title,
                status=EpisodeStatus.FAILED,
                source_url=episode.source_url,
                file_path=None,
                error_message=last_error,
            )
        )
        return last_error

    def _build_destination_path(
        self,
        series: Series,
        season: Season,
        episode: Episode,
        media: MediaLocator,
    ) -> Path:
        safe_series = _sanitize_segment(series.title)
        ss = f"{season.number:02d}"
        ee = f"{episode.number:02d}"
        raw_title = (
            episode.title.strip()
            if episode.title and episode.title.strip()
            else series.title
        )
        safe_title = _sanitize_segment(raw_title)
        ext = _extract_extension(media)
        filename = f"S{ss}E{ee} - {safe_title}.{ext}"
        return self._library_root / safe_series / str(season.number) / filename

    def _save_job_progress(
        self, job: DownloadJob, season_id: str, status: JobStatus
    ) -> DownloadJob:
        episodes = self._library.list_episodes(season_id)
        completed_count = sum(
            1 for ep in episodes if ep.status == EpisodeStatus.COMPLETED
        )
        failed_count = sum(1 for ep in episodes if ep.status == EpisodeStatus.FAILED)
        return self._jobs.save(
            DownloadJob(
                id=job.id,
                source_url=job.source_url,
                adapter_id=job.adapter_id,
                status=status,
                series_id=job.series_id,
                season_id=season_id,
                total_episodes=len(episodes),
                completed_episodes=completed_count,
                failed_episodes=failed_count,
                error_message=job.error_message,
            )
        )

    def _fail_job(self, job: DownloadJob, error_message: str) -> None:
        self._jobs.save(
            DownloadJob(
                id=job.id,
                source_url=job.source_url,
                adapter_id=job.adapter_id,
                status=JobStatus.FAILED,
                series_id=job.series_id,
                season_id=job.season_id,
                total_episodes=job.total_episodes,
                completed_episodes=job.completed_episodes,
                failed_episodes=job.failed_episodes,
                error_message=error_message,
            )
        )


def _extract_extension(media: MediaLocator) -> str:
    if media.suggested_filename:
        suffix = Path(media.suggested_filename).suffix.lstrip(".")
        if suffix and suffix.lower() not in {"m3u8", "m3u", "mpd"}:
            return _sanitize_segment(suffix)
    parsed_path = urlparse(media.url).path
    if parsed_path:
        suffix = Path(parsed_path).suffix.lstrip(".")
        # HLS/DASH manifests are remuxed to a container file by yt-dlp.
        if suffix and suffix.lower() not in {"m3u8", "m3u", "mpd"}:
            return _sanitize_segment(suffix)
    return "mp4"


def _sanitize_segment(value: str) -> str:
    cleaned = value.replace("/", "_").replace("\\", "_").replace("\x00", "").strip()
    if cleaned in {"", ".", ".."}:
        return "_"
    return cleaned
