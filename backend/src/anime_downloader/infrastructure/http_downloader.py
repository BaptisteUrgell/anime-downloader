from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen

from anime_downloader.domain.model import MediaLocator
from anime_downloader.domain.ports import ProgressCallback


class HttpMediaDownloader:
    def __init__(self, timeout: float = 60.0, chunk_size: int = 65536) -> None:
        self._timeout = timeout
        self._chunk_size = chunk_size

    def download(
        self,
        media: MediaLocator,
        destination: str,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> str:
        dest_path = Path(destination).expanduser().resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = dest_path.with_name(f".{dest_path.name}.part")
        request = Request(media.url, headers=dict(media.headers), method="GET")
        try:
            with urlopen(request, timeout=self._timeout) as response, temp_path.open(
                "wb"
            ) as out_file:
                total_header = response.headers.get("Content-Length")
                try:
                    total = int(total_header) if total_header else 0
                except ValueError:
                    total = 0
                downloaded = 0
                if on_progress is not None:
                    on_progress(0.0)
                while chunk := response.read(self._chunk_size):
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if on_progress is not None and total > 0:
                        on_progress(min(100.0, downloaded * 100.0 / total))
            temp_path.replace(dest_path)
            if on_progress is not None:
                on_progress(100.0)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return str(dest_path)


class FakeMediaDownloader:
    def __init__(self, payload: bytes = b"fake-media") -> None:
        self._payload = payload

    def download(
        self,
        media: MediaLocator,
        destination: str,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> str:
        _ = media
        dest_path = Path(destination).expanduser().resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if on_progress is not None:
            on_progress(0.0)
            on_progress(100.0)
        dest_path.write_bytes(self._payload)
        return str(dest_path)
