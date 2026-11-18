from __future__ import annotations

from pathlib import Path

import httpx

from anime_downloader.api.deps import build_default_registry
from anime_downloader.domain.model import EpisodeRef, SourceUrl
from anime_downloader.infrastructure.anime_sama.adapter import AnimeSamaAdapter
from anime_downloader.infrastructure.anime_sama.provider import AnimeSamaProvider

FIXTURES = Path(__file__).parent / "fixtures"
SEASON_URL = "https://anime-sama.to/catalogue/dreamland/saison1/vostfr/"


def test_default_registry_resolves_anime_sama():
    registry = build_default_registry()
    adapter = registry.resolve(SourceUrl.parse(SEASON_URL))
    assert adapter.adapter_id == "anime-sama"


def test_adapter_discover_maps_domain_types():
    html = (FIXTURES / "season_page.html").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    provider = AnimeSamaProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = AnimeSamaAdapter(provider=provider)
    discovery = adapter.discover_season(SourceUrl.parse(SEASON_URL))
    assert discovery.series_title == "dreamland-vostfr"
    assert discovery.season_number == 1
    assert discovery.episode_count == 2
    assert all(ep.source_url == SEASON_URL for ep in discovery.episodes)
    assert discovery.episodes[0].number == 1
    provider.close()


def test_adapter_next_episode_stays_within_season():
    html = (FIXTURES / "season_page.html").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    provider = AnimeSamaProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = AnimeSamaAdapter(provider=provider)
    adapter.discover_season(SourceUrl.parse(SEASON_URL))
    nxt = adapter.next_episode(
        EpisodeRef(source_url=SEASON_URL, number=1, title=None)
    )
    assert nxt is not None
    assert nxt.source_url == SEASON_URL
    assert nxt.number == 2
    # End of season → None even if page advertises ctSaisonSuivante
    assert (
        adapter.next_episode(
            EpisodeRef(source_url=SEASON_URL, number=2, title=None)
        )
        is None
    )
    provider.close()