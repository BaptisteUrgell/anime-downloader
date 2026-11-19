from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from anime_downloader.api.deps import build_default_registry
from anime_downloader.domain.model import EpisodeRef, SourceUrl
from anime_downloader.infrastructure.anime_sama.adapter import AnimeSamaAdapter
from anime_downloader.infrastructure.anime_sama.provider import AnimeSamaError, AnimeSamaProvider

FIXTURES = Path(__file__).parent / "fixtures"
SEASON_URL = "https://anime-sama.to/catalogue/dreamland/saison1/vostfr/"
HELLS_SEASON_URL = "https://anime-sama.to/catalogue/hells-paradise/saison1/vostfr/"
DREAMLAND_OEUVRE = """
<h1 id="titreOeuvre" class="oe-titre">Dreamland</h1>
<p class="oe-meta">2021<span class="oe-point">·</span>Série TV</p>
"""


def _season_html() -> str:
    return (FIXTURES / "season_page.html").read_text(encoding="utf-8")


def _oeuvre_html() -> str:
    return (FIXTURES / "oeuvre_page.html").read_text(encoding="utf-8")


def _adapter(season_html: str, oeuvre_html: str) -> tuple[AnimeSamaAdapter, AnimeSamaProvider]:
    def handler(request: httpx.Request) -> httpx.Response:
        # /catalogue/{slug}/ is the oeuvre page; season URLs are deeper.
        if request.url.path.rstrip("/").count("/") == 2:
            return httpx.Response(200, text=oeuvre_html)
        return httpx.Response(200, text=season_html)

    provider = AnimeSamaProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    return AnimeSamaAdapter(provider=provider), provider


def test_default_registry_resolves_anime_sama():
    registry = build_default_registry()
    adapter = registry.resolve(SourceUrl.parse(SEASON_URL))
    assert adapter.adapter_id == "anime-sama"


def test_adapter_discover_maps_domain_types():
    adapter, provider = _adapter(_season_html(), DREAMLAND_OEUVRE)
    discovery = adapter.discover_season(SourceUrl.parse(SEASON_URL))
    assert discovery.series_title == "Dreamland"
    assert discovery.release_year == 2021
    assert discovery.season_number == 1
    assert discovery.episode_count == 2
    assert all(ep.source_url == SEASON_URL for ep in discovery.episodes)
    assert discovery.episodes[0].number == 1
    provider.close()


def test_adapter_discover_uses_oeuvre_title_and_year():
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path.rstrip("/") == "/catalogue/hells-paradise":
            return httpx.Response(200, text=_oeuvre_html())
        return httpx.Response(200, text=_season_html())

    provider = AnimeSamaProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = AnimeSamaAdapter(provider=provider)
    discovery = adapter.discover_season(SourceUrl.parse(HELLS_SEASON_URL))
    assert discovery.series_title == "Hell's Paradise"
    assert discovery.release_year == 2023
    assert discovery.season_number == 1
    assert "https://anime-sama.to/catalogue/hells-paradise/" in requested
    provider.close()


def test_adapter_discover_missing_year_leaves_release_year_none():
    oeuvre = """
    <h1 id="titreOeuvre">Hell's Paradise</h1>
    <p class="oe-meta">Série TV<span class="oe-point">·</span>MAPPA</p>
    """
    adapter, provider = _adapter(_season_html(), oeuvre)
    discovery = adapter.discover_season(SourceUrl.parse(HELLS_SEASON_URL))
    assert discovery.series_title == "Hell's Paradise"
    assert discovery.release_year is None
    provider.close()


def test_adapter_discover_missing_title_fails():
    adapter, provider = _adapter(_season_html(), '<p class="oe-meta">2023</p>')
    with pytest.raises(AnimeSamaError):
        adapter.discover_season(SourceUrl.parse(HELLS_SEASON_URL))
    provider.close()


def test_adapter_next_episode_stays_within_season():
    adapter, provider = _adapter(_season_html(), DREAMLAND_OEUVRE)
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