from __future__ import annotations

import pytest

from anime_downloader.application.preview_season import preview_season
from anime_downloader.domain.errors import (
    DiscoveryFailed,
    InvalidSourceUrl,
    NoAdapterFound,
)
from anime_downloader.domain.model import (
    EpisodeRef,
    MediaLocator,
    SeasonDiscovery,
    SourceUrl,
)
from anime_downloader.infrastructure.adapter_registry import AdapterRegistry
from anime_downloader.infrastructure.demo_adapter import DemoAdapter


class _FailingDiscoveryAdapter:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    @property
    def adapter_id(self) -> str:
        return "failing"

    def matches(self, url: SourceUrl) -> bool:
        return url.host == "broken.local"

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        raise self._exc

    def resolve_media(self, episode: EpisodeRef) -> MediaLocator:
        raise NotImplementedError

    def next_episode(self, episode: EpisodeRef) -> EpisodeRef | None:
        return None


def test_preview_season_returns_discovery_for_demo_url() -> None:
    registry = AdapterRegistry([DemoAdapter(episode_count=3)])

    discovery = preview_season("https://demo.local/season/frieren/1", registry)

    assert discovery.series_title == "frieren"
    assert discovery.season_number == 1
    assert discovery.episode_count == 3
    assert [ep.number for ep in discovery.episodes] == [1, 2, 3]


@pytest.mark.parametrize("bad_url", ["", "   ", "not-a-url", "ftp://demo.local/season/x/1"])
def test_preview_season_rejects_invalid_url(bad_url: str) -> None:
    registry = AdapterRegistry([DemoAdapter()])

    with pytest.raises(InvalidSourceUrl):
        preview_season(bad_url, registry)


def test_preview_season_raises_when_no_adapter_matches() -> None:
    registry = AdapterRegistry([DemoAdapter()])

    with pytest.raises(NoAdapterFound):
        preview_season("https://unknown.example/season/frieren/1", registry)


def test_preview_season_wraps_adapter_error_in_discovery_failed() -> None:
    registry = AdapterRegistry(
        [
            DemoAdapter(),
            _FailingDiscoveryAdapter(RuntimeError("upstream parse error")),
        ]
    )

    with pytest.raises(DiscoveryFailed):
        preview_season("https://demo.local/season/missing-number", registry)

    with pytest.raises(DiscoveryFailed, match="upstream parse error"):
        preview_season("https://broken.local/season/show/1", registry)


def test_preview_season_propagates_domain_discovery_failed() -> None:
    registry = AdapterRegistry(
        [_FailingDiscoveryAdapter(DiscoveryFailed("explicit discovery failure"))]
    )

    with pytest.raises(DiscoveryFailed, match="explicit discovery failure"):
        preview_season("https://broken.local/season/show/1", registry)
