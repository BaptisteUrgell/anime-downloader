from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
from yt_dlp.utils import DownloadError

from anime_downloader.infrastructure.anime_sama.provider import (
    AnimeSamaError,
    AnimeSamaProvider,
    PermanentMediaError,
    SourceCandidate,
    TokenExpiredError,
)


FIXTURES = Path(__file__).parent / "fixtures"
SEASON_URL = "https://anime-sama.to/catalogue/dreamland/saison1/vostfr/"


def _html() -> str:
    return (FIXTURES / "season_page.html").read_text(encoding="utf-8")


def test_matches_season_url():
    provider = AnimeSamaProvider()
    assert provider.matches(SEASON_URL) is True
    assert provider.matches("https://anime-sama.to/catalogue/dreamland/") is False
    assert provider.matches("https://other.example/catalogue/x/saison1/vostfr/") is False
    provider.close()


OEUVRE_URL = "https://anime-sama.to/catalogue/hells-paradise/"


def _oeuvre_html() -> str:
    return (FIXTURES / "oeuvre_page.html").read_text(encoding="utf-8")


def test_fetch_oeuvre_meta_parses_title_and_year():
    html = _oeuvre_html()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == OEUVRE_URL
        return httpx.Response(200, text=html)

    provider = AnimeSamaProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    title, year = provider.fetch_oeuvre_meta(OEUVRE_URL)
    assert title == "Hell's Paradise"
    assert year == 2023
    provider.close()


def test_fetch_oeuvre_meta_missing_title_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text='<p class="oe-meta">2023</p>')

    provider = AnimeSamaProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(AnimeSamaError, match="titreOeuvre"):
        provider.fetch_oeuvre_meta(OEUVRE_URL)
    provider.close()


def test_fetch_oeuvre_meta_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = AnimeSamaProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(AnimeSamaError):
        provider.fetch_oeuvre_meta(OEUVRE_URL)
    provider.close()


def test_discover_season_filters_dead_hosts_and_caches(monkeypatch: pytest.MonkeyPatch):
    html = _html()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == SEASON_URL
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = AnimeSamaProvider()
    provider.client = client

    episodes = provider.discover_season(SEASON_URL)
    assert len(episodes) == 2
    assert episodes[0].number == 1
    assert episodes[0].season_url == SEASON_URL
    assert episodes[0].token == "test-token-abc"
    assert episodes[0].next_season_url == (
        "https://anime-sama.to/catalogue/dreamland/saison2/vostfr/"
    )
    # sibnet.ru marked mort → eps2 dropped; eps1 ansembed and eps3 uqload stay
    hosts = {s.host for s in episodes[0].sources}
    assert "sibnet.ru" not in hosts
    assert "ansembed.net" in hosts
    assert "uqload.vc" in hosts
    assert provider.get_cached_season(SEASON_URL) is not None
    provider.close()


def test_discover_season_tolerates_malformed_optional_page_json():
    html = _html().replace(
        'var ctSaisonSuivante = "/catalogue/dreamland/saison2/vostfr/";',
        "var ctSaisonSuivante = '/catalogue/dreamland/saison2/vostfr/';",
    ).replace(
        'var lecteursInfos = {"sibnet.ru":{"mort":true},"ansembed.net":{"mort":false},"uqload.vc":{"mort":false}};',
        "var lecteursInfos = {sibnet.ru: {mort: true}};",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    provider = AnimeSamaProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    episodes = provider.discover_season(SEASON_URL)
    assert len(episodes) == 2
    assert episodes[0].number == 1
    assert episodes[0].next_season_url is None
    assert {source.host for source in episodes[0].sources} >= {
        "ansembed.net",
        "sibnet.ru",
        "uqload.vc",
    }
    provider.close()


def test_resolve_embed_url_get_params():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/api/lien.php":
            assert request.url.params["j"] == "tok"
            assert request.url.params["l"] == "100"
            return httpx.Response(200, json="https://embed.example/v/100")
        return httpx.Response(404)

    provider = AnimeSamaProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    url = provider._resolve_embed_url("100", "tok", SEASON_URL)
    assert url == "https://embed.example/v/100"
    provider.close()


def test_resolve_embed_url_dict_payload_and_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        l = request.url.params.get("l")
        if l == "ok":
            return httpx.Response(200, json={"lien": "https://embed.example/ok"})
        if l == "gone":
            return httpx.Response(410)
        if l == "denied":
            return httpx.Response(403)
        return httpx.Response(500)

    provider = AnimeSamaProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    assert (
        provider._resolve_embed_url("ok", "tok", SEASON_URL)
        == "https://embed.example/ok"
    )
    with pytest.raises(PermanentMediaError):
        provider._resolve_embed_url("gone", "tok", SEASON_URL)
    with pytest.raises(TokenExpiredError):
        provider._resolve_embed_url("denied", "tok", SEASON_URL)
    provider.close()


def _stream(**overrides: object) -> dict:
    info: dict[str, object] = {
        "url": "https://cdn.example/best.mp4",
        "width": 1920,
        "height": 1080,
        "fps": 60.0,
        "protocol": "https",
        "http_headers": {"Cookie": "x=1"},
    }
    info.update(overrides)
    return info


def test_resolve_media_picks_first_working_player(monkeypatch: pytest.MonkeyPatch):
    html = _html()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/vostfr/") or str(request.url) == SEASON_URL:
            return httpx.Response(200, text=html)
        if request.url.path == "/api/lien.php":
            link = request.url.params["l"]
            if link == "100":
                return httpx.Response(200, json="https://embed.example/bad")
            return httpx.Response(200, json=f"https://embed.example/{link}")
        return httpx.Response(404)

    provider = AnimeSamaProvider(max_retries_per_player=1, retry_delay=0)
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    provider.discover_season(SEASON_URL)

    def fake_extract(embed_url: str) -> dict:
        if embed_url.endswith("/bad"):
            raise PermanentMediaError("removed")
        return _stream()

    monkeypatch.setattr(provider, "_extract_best_stream", fake_extract)
    media = provider.resolve_media_for_episode(SEASON_URL, 1)
    assert media.url == "https://cdn.example/best.mp4"
    assert media.resolution == "1920x1080"
    assert media.fps == 60.0
    assert media.width == 1920
    assert media.height == 1080
    assert media.protocol == "https"
    assert media.player == 3
    assert media.host == "uqload.vc"
    assert media.headers["Referer"].startswith("https://embed.example/")
    assert media.headers["Referer"] == "https://embed.example/300"
    assert media.headers["Cookie"] == "x=1"
    assert media.headers["User-Agent"] == provider.user_agent
    provider.close()


def test_resolve_media_rediscovers_on_cache_miss(monkeypatch: pytest.MonkeyPatch):
    html = _html()

    def handler(request: httpx.Request) -> httpx.Response:
        if "catalogue" in str(request.url):
            return httpx.Response(200, text=html)
        if request.url.path == "/api/lien.php":
            return httpx.Response(200, json="https://embed.example/100")
        return httpx.Response(404)

    provider = AnimeSamaProvider(max_retries_per_player=1, retry_delay=0)
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    # no prior discover_season → cache miss path
    monkeypatch.setattr(
        provider,
        "_extract_best_stream",
        lambda embed_url: _stream(
            url="https://cdn.example/ep.mp4",
            width=1280,
            height=720,
            fps=24.0,
            http_headers={},
        ),
    )
    media = provider.resolve_media_for_episode(SEASON_URL, 2)
    assert media.url == "https://cdn.example/ep.mp4"
    assert media.resolution == "1280x720"
    assert provider.get_cached_season(SEASON_URL) is not None
    provider.close()


def test_resolve_media_skips_permanent_lien_without_retry(monkeypatch: pytest.MonkeyPatch):
    html = _html()
    extracted: list[str] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "catalogue" in str(request.url):
            return httpx.Response(200, text=html)
        if request.url.path == "/api/lien.php":
            link = request.url.params["l"]
            if link == "101":
                return httpx.Response(410)
            return httpx.Response(200, json=f"https://embed.example/{link}")
        return httpx.Response(404)

    def fake_extract(embed_url: str) -> dict:
        extracted.append(embed_url)
        return _stream(url="https://cdn.example/next.mp4", http_headers={})

    monkeypatch.setattr(time, "sleep", lambda delay: sleeps.append(delay))
    provider = AnimeSamaProvider(max_retries_per_player=3, retry_delay=1.5)
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(provider, "_extract_best_stream", fake_extract)
    media = provider.resolve_media_for_episode(SEASON_URL, 2)
    assert media.url == "https://cdn.example/next.mp4"
    assert media.player == 2
    assert media.host == "uqload.vc"
    assert extracted == ["https://embed.example/201"]
    assert sleeps == []
    provider.close()


def test_resolve_media_retries_transient_errors_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
):
    html = _html()
    sleeps: list[float] = []
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "catalogue" in str(request.url):
            return httpx.Response(200, text=html)
        if request.url.path == "/api/lien.php":
            return httpx.Response(200, json="https://embed.example/ok")
        return httpx.Response(404)

    def fake_extract(embed_url: str) -> dict:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("timeout")
        return _stream(url="https://cdn.example/retry.mp4", http_headers={})

    monkeypatch.setattr(time, "sleep", lambda delay: sleeps.append(delay))
    provider = AnimeSamaProvider(max_retries_per_player=3, retry_delay=0.5)
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(provider, "_extract_best_stream", fake_extract)
    media = provider.resolve_media_for_episode(SEASON_URL, 2)
    assert media.url == "https://cdn.example/retry.mp4"
    assert attempts["n"] == 3
    assert sleeps == [0.5, 1.0]
    provider.close()


def test_resolve_media_refreshes_expired_token_once(monkeypatch: pytest.MonkeyPatch):
    html_old = _html().replace("test-token-abc", "old-token")
    html_new = _html().replace("test-token-abc", "new-token")
    season_fetches = {"n": 0}
    tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "catalogue" in str(request.url):
            season_fetches["n"] += 1
            html = html_old if season_fetches["n"] == 1 else html_new
            return httpx.Response(200, text=html)
        if request.url.path == "/api/lien.php":
            token = request.url.params["j"]
            tokens.append(token)
            if token == "old-token":
                return httpx.Response(403)
            return httpx.Response(200, json="https://embed.example/fresh")
        return httpx.Response(404)

    provider = AnimeSamaProvider(max_retries_per_player=1, retry_delay=0)
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    provider.discover_season(SEASON_URL)
    monkeypatch.setattr(
        provider,
        "_extract_best_stream",
        lambda embed_url: _stream(url="https://cdn.example/fresh.mp4", http_headers={}),
    )
    media = provider.resolve_media_for_episode(SEASON_URL, 2)
    assert media.url == "https://cdn.example/fresh.mp4"
    assert tokens == ["old-token", "new-token"]
    assert season_fetches["n"] == 2
    assert provider.get_cached_season(SEASON_URL).token == "new-token"
    provider.close()


def test_resolve_media_does_not_refresh_token_twice(monkeypatch: pytest.MonkeyPatch):
    html = _html()
    season_fetches = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "catalogue" in str(request.url):
            season_fetches["n"] += 1
            return httpx.Response(200, text=html)
        if request.url.path == "/api/lien.php":
            return httpx.Response(401)
        return httpx.Response(404)

    provider = AnimeSamaProvider(max_retries_per_player=3, retry_delay=0)
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(
        provider,
        "_extract_best_stream",
        lambda embed_url: _stream(),
    )
    with pytest.raises(AnimeSamaError):
        provider.resolve_media_for_episode(SEASON_URL, 1)
    # cache miss discover + one refresh, even though every lien.php stays 401
    assert season_fetches["n"] == 2
    provider.close()


def test_resolve_media_raises_when_every_player_fails(monkeypatch: pytest.MonkeyPatch):
    html = _html()

    def handler(request: httpx.Request) -> httpx.Response:
        if "catalogue" in str(request.url):
            return httpx.Response(200, text=html)
        if request.url.path == "/api/lien.php":
            return httpx.Response(200, json="https://embed.example/gone")
        return httpx.Response(404)

    def always_removed(embed_url: str) -> dict:
        raise PermanentMediaError("removed")

    provider = AnimeSamaProvider(max_retries_per_player=2, retry_delay=0)
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(provider, "_extract_best_stream", always_removed)
    with pytest.raises(AnimeSamaError):
        provider.resolve_media_for_episode(SEASON_URL, 2)
    provider.close()


def test_resolve_media_unknown_episode_raises(monkeypatch: pytest.MonkeyPatch):
    html = _html()

    def handler(request: httpx.Request) -> httpx.Response:
        if "catalogue" in str(request.url):
            return httpx.Response(200, text=html)
        return httpx.Response(404)

    provider = AnimeSamaProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(AnimeSamaError):
        provider.resolve_media_for_episode(SEASON_URL, 99)
    provider.close()


def test_extract_best_stream_sorts_quality_and_maps_download_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    created: dict[str, object] = {}

    class FakeYDL:
        def __init__(self, params: dict) -> None:
            created["params"] = params

        def __enter__(self) -> FakeYDL:
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def extract_info(self, url: str, download: bool = False) -> dict:
            created["url"] = url
            created["download"] = download
            return {"url": "https://cdn.example/direct.mp4"}

    monkeypatch.setattr(
        "anime_downloader.infrastructure.anime_sama.provider.yt_dlp.YoutubeDL",
        FakeYDL,
    )
    provider = AnimeSamaProvider()
    info = provider._extract_best_stream("https://embed.example/x")
    assert info["url"] == "https://cdn.example/direct.mp4"
    params = created["params"]
    assert isinstance(params, dict)
    assert "protocol!*=m3u8" in params["format"]
    assert "best" in params["format"]
    assert params["format_sort"] == ["res", "fps", "tbr"]
    assert params["format_sort_force"] is True
    assert params["http_headers"] == {
        "User-Agent": provider.user_agent,
        "Referer": "https://embed.example/x",
    }
    assert created["download"] is False
    assert created["url"] == "https://embed.example/x"

    class MissingYDL(FakeYDL):
        def extract_info(self, url: str, download: bool = False) -> dict:
            message = created.get("message")
            raise DownloadError(str(message))

    monkeypatch.setattr(
        "anime_downloader.infrastructure.anime_sama.provider.yt_dlp.YoutubeDL",
        MissingYDL,
    )
    for message in (
        "HTTP Error 404: Not Found",
        "This video has been removed",
        "Video unavailable",
    ):
        created["message"] = message
        with pytest.raises(PermanentMediaError):
            provider._extract_best_stream("https://embed.example/missing")

    for message in ("ERROR: timed out", "HTTP Error 503: Service Temporarily Unavailable"):
        created["message"] = message
        with pytest.raises(DownloadError):
            provider._extract_best_stream("https://embed.example/slow")
    provider.close()


def test_media_from_stream_prefers_requested_format_and_embed_referer():
    provider = AnimeSamaProvider()
    media = provider._media_from_stream(
        {
            "requested_formats": [
                {"url": "https://cdn.example/audio.m4a"},
                {"url": "https://cdn.example/video.mp4"},
            ],
            "width": 1280,
            "height": 720,
            "fps": 24,
            "protocol": "https",
            "http_headers": {"Referer": "https://other.example/", "Cookie": "a=b"},
        },
        "https://embed.example/v",
        SourceCandidate(player=2, link_id="201", host="uqload.vc"),
    )
    assert media.url == "https://cdn.example/video.mp4"
    assert media.resolution == "1280x720"
    assert media.fps == 24.0
    assert media.player == 2
    assert media.host == "uqload.vc"
    assert media.headers["Referer"] == "https://embed.example/v"
    assert media.headers["Cookie"] == "a=b"
    assert media.headers["User-Agent"] == provider.user_agent
    provider.close()