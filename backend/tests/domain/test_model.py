import pytest
from anime_downloader.domain.errors import InvalidSourceUrl
from anime_downloader.domain.model import EpisodeStatus, SourceUrl


def test_source_url_parses_https():
    url = SourceUrl.parse("https://example.com/anime/x/saison-1/episode-01")
    assert str(url) == "https://example.com/anime/x/saison-1/episode-01"


def test_source_url_rejects_empty():
    with pytest.raises(InvalidSourceUrl):
        SourceUrl.parse("not a url")


def test_episode_status_values():
    assert EpisodeStatus.PENDING.value == "pending"
    assert EpisodeStatus.COMPLETED.value == "completed"