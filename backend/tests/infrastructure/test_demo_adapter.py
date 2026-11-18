import pytest
from anime_downloader.domain.errors import NoAdapterFound
from anime_downloader.domain.model import SourceUrl
from anime_downloader.infrastructure.adapter_registry import AdapterRegistry
from anime_downloader.infrastructure.demo_adapter import DemoAdapter


def test_demo_adapter_discovers_fixed_episode_count():
    adapter = DemoAdapter(episode_count=3)
    url = SourceUrl.parse("https://demo.local/season/demo-show/1")
    discovery = adapter.discover_season(url)
    assert discovery.episode_count == 3
    assert discovery.series_title == "demo-show"
    assert discovery.season_number == 1
    assert discovery.episodes[0].number == 1


def test_registry_resolves_demo():
    registry = AdapterRegistry([DemoAdapter()])
    adapter = registry.resolve(SourceUrl.parse("https://demo.local/season/x/1"))
    assert adapter.adapter_id == "demo"


def test_registry_raises_when_unknown():
    registry = AdapterRegistry([DemoAdapter()])
    with pytest.raises(NoAdapterFound):
        registry.resolve(SourceUrl.parse("https://unknown.example/a"))