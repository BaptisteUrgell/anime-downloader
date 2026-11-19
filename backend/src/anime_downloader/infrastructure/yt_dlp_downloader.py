from __future__ import annotations

from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError

from anime_downloader.domain.model import MediaLocator
from anime_downloader.domain.ports import ProgressCallback


class YtDlpMediaDownloader:
    """Download progressive or HLS media via yt-dlp into a container file (mp4/mkv)."""

    def __init__(self, merge_output_format: str = "mp4") -> None:
        self._merge_output_format = merge_output_format

    def download(
        self,
        media: MediaLocator,
        destination: str,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> str:
        dest_path = Path(destination).expanduser().resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.suffix.lower() in {".m3u8", ".mpd", ".m3u", ""}:
            dest_path = dest_path.with_suffix(f".{self._merge_output_format}")

        # yt-dlp appends the extension from the template; strip ours and restore after.
        outtmpl = str(dest_path.with_suffix("")) + ".%(ext)s"
        temp_glob_stem = dest_path.with_suffix("")
        options: dict = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "format": (
                "best[ext=mp4]/best[protocol^=http][protocol!*=m3u8]/"
                "bv*+ba/best"
            ),
            "merge_output_format": self._merge_output_format,
            "outtmpl": {"default": outtmpl},
            "http_headers": dict(media.headers),
            "retries": 3,
            "fragment_retries": 3,
            "overwrites": True,
        }
        if on_progress is not None:
            on_progress(0.0)
            options["progress_hooks"] = [_make_progress_hook(on_progress)]

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([media.url])
        except DownloadError:
            for leftover in dest_path.parent.glob(f"{temp_glob_stem.name}.*"):
                if leftover != dest_path:
                    leftover.unlink(missing_ok=True)
            raise

        if dest_path.is_file() and dest_path.stat().st_size > 0:
            if on_progress is not None:
                on_progress(100.0)
            return str(dest_path)

        # yt-dlp may have written a different extension (e.g. mkv).
        candidates = sorted(
            (
                path
                for path in dest_path.parent.glob(f"{temp_glob_stem.name}.*")
                if path.is_file() and path.suffix.lower() not in {".part", ".ytdl"}
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise FileNotFoundError(
                f"yt-dlp produced no output for {media.url} -> {dest_path}"
            )
        written = candidates[0]
        if written != dest_path:
            written.replace(dest_path)
        if on_progress is not None:
            on_progress(100.0)
        return str(dest_path)


def _make_progress_hook(on_progress: ProgressCallback):
    def hook(status: dict) -> None:
        if status.get("status") != "downloading":
            return
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        downloaded = status.get("downloaded_bytes")
        if not isinstance(total, (int, float)) or total <= 0:
            return
        if not isinstance(downloaded, (int, float)):
            return
        on_progress(min(100.0, float(downloaded) * 100.0 / float(total)))

    return hook
