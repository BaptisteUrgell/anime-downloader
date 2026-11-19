from anime_downloader.domain.model import EpisodeRef, SeasonDiscovery, Series


def test_season_discovery_carries_release_year():
    discovery = SeasonDiscovery(
        series_title="Hell's Paradise",
        season_number=1,
        release_year=2023,
        episodes=(EpisodeRef(source_url="https://x", number=1),),
    )
    assert discovery.release_year == 2023


def test_series_carries_release_year():
    series = Series(id="s1", title="Hell's Paradise", release_year=2023)
    assert series.release_year == 2023


def test_release_year_defaults_to_none():
    discovery = SeasonDiscovery(
        series_title="X",
        season_number=1,
        episodes=(),
    )
    assert discovery.release_year is None
    assert Series(id="s", title="X").release_year is None