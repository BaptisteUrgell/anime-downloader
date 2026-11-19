from __future__ import annotations

from pathlib import Path

import pytest

from anime_downloader.api.deps import DefaultMediaDownloader, _is_hls_or_dash_url
from anime_downloader.domain.model import MediaLocator
from anime_downloader.infrastructure.yt_dlp_downloader import YtDlpMediaDownloader


def test_is_hls_or_dash_url_detects_manifests() -> None:
    assert _is_hls_or_dash_url("https://cdn.example/ep.m3u8") is True
    assert _is_hls_or_dash_url("https://cdn.example/dash/stream.mpd") is True
    assert _is_hls_or_dash_url("https://cdn.example/video.mp4") is False


def test_default_downloader_routes_hls_to_ytdlp(tmp_path: Path) -> None:
    calls: list[str] = []

    class RecordingYtDlp:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            calls.append(media.url)
            path = Path(destination).with_suffix(".mp4")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"merged-mp4")
            return str(path)

    class BoomHttp:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            raise AssertionError("HTTP downloader must not fetch HLS manifests")

    downloader = DefaultMediaDownloader(
        http_downloader=BoomHttp(),  # type: ignore[arg-type]
        ytdlp_downloader=RecordingYtDlp(),  # type: ignore[arg-type]
    )
    dest = tmp_path / "lib" / "show" / "1" / "S01E01 - show.m3u8"
    written = downloader.download(
        MediaLocator(url="https://cdn.example/ep/index.m3u8"),
        str(dest),
    )
    assert calls == ["https://cdn.example/ep/index.m3u8"]
    assert written.endswith(".mp4")
    assert Path(written).read_bytes() == b"merged-mp4"


def test_ytdlp_downloader_writes_mp4_via_youtube_dl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "out" / "S01E01 - show.m3u8"
    written_holder: dict[str, Path] = {}

    class FakeYDL:
        def __init__(self, options: dict) -> None:
            self.options = options

        def __enter__(self) -> FakeYDL:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def download(self, urls: list[str]) -> None:
            assert urls == ["https://cdn.example/ep.m3u8"]
            outtmpl = self.options["outtmpl"]["default"]
            assert "%(ext)s" in outtmpl
            target = Path(outtmpl.replace("%(ext)s", "mp4"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"real-video")
            written_holder["path"] = target

    monkeypatch.setattr(
        "anime_downloader.infrastructure.yt_dlp_downloader.yt_dlp.YoutubeDL",
        FakeYDL,
    )
    downloader = YtDlpMediaDownloader()
    written = downloader.download(
        MediaLocator(
            url="https://cdn.example/ep.m3u8",
            headers={"Referer": "https://embed.example/"},
        ),
        str(dest),
    )
    assert Path(written).suffix == ".mp4"
    assert Path(written).read_bytes() == b"real-video"
    assert written_holder["path"].name.endswith(".mp4")


def test_ytdlp_downloader_renames_mkv_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "out" / "S01E01 - show.mp4"

    class FakeYDL:
        def __init__(self, options: dict) -> None:
            self.options = options

        def __enter__(self) -> FakeYDL:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def download(self, urls: list[str]) -> None:
            _ = urls
            outtmpl = self.options["outtmpl"]["default"]
            target = Path(outtmpl.replace("%(ext)s", "mkv"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"mkv-bytes")

    monkeypatch.setattr(
        "anime_downloader.infrastructure.yt_dlp_downloader.yt_dlp.YoutubeDL",
        FakeYDL,
    )
    written = YtDlpMediaDownloader().download(
        MediaLocator(url="https://cdn.example/ep.m3u8"),
        str(dest),
    )
    assert written == str(dest.resolve())
    assert dest.read_bytes() == b"mkv-bytes"
