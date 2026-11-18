from __future__ import annotations

from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer

from anime_downloader.api.deps import DefaultMediaDownloader
from anime_downloader.domain.model import MediaLocator
from anime_downloader.infrastructure.http_downloader import HttpMediaDownloader
from anime_downloader.infrastructure.worker import DownloadWorker, JobDownloadProgress


def test_http_downloader_reports_percent_from_content_length(tmp_path: Path) -> None:
    payload = b"x" * 10_000
    percents: list[float] = []

    class FastLocalHTTPServer(ThreadingHTTPServer):
        def server_bind(self) -> None:
            TCPServer.server_bind(self)
            host, port = self.server_address[:2]
            self.server_name = str(host)
            self.server_port = int(port)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = FastLocalHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        host, port = server.server_address[:2]
        dest = tmp_path / "ep.mp4"
        HttpMediaDownloader(chunk_size=1024).download(
            MediaLocator(url=f"http://{host}:{port}/v.mp4"),
            str(dest),
            on_progress=percents.append,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert percents[0] == 0.0
    assert percents[-1] == 100.0
    assert any(0.0 < p < 100.0 for p in percents)


def test_worker_exposes_download_progress_snapshot() -> None:
    worker = DownloadWorker.__new__(DownloadWorker)
    worker._lock = threading.Lock()
    worker._download_progress = {}
    worker._set_download_progress("job-1", episode_number=3, percent=42.5)
    snap = worker.get_download_progress("job-1")
    assert snap == JobDownloadProgress(episode_number=3, percent=42.5)
    worker._clear_download_progress("job-1")
    assert worker.get_download_progress("job-1") is None


def test_default_downloader_forwards_progress_to_http(tmp_path: Path) -> None:
    seen: list[float] = []

    class RecordingHttp:
        def download(self, media, destination, *, on_progress=None):
            if on_progress is not None:
                on_progress(12.0)
                on_progress(100.0)
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"ok")
            return str(path)

    downloader = DefaultMediaDownloader(http_downloader=RecordingHttp())  # type: ignore[arg-type]
    dest = tmp_path / "a.mp4"
    downloader.download(
        MediaLocator(url="https://cdn.example/a.mp4"),
        str(dest),
        on_progress=seen.append,
    )
    assert seen == [12.0, 100.0]
