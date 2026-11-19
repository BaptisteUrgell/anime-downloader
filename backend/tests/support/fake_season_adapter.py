from __future__ import annotations

from urllib.parse import urlparse

from anime_downloader.domain.model import EpisodeRef, MediaLocator, SeasonDiscovery, SourceUrl


class FakeSeasonAdapter:
    def __init__(self, episode_count: int = 3, release_year: int | None = 2020) -> None:
        self._episode_count = episode_count
        self._release_year = release_year

    @property
    def adapter_id(self) -> str:
        return "fake"

    def matches(self, url: SourceUrl) -> bool:
        return url.host == "fake.local"

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        series_title, season_number = _parse(url)
        base = f"https://fake.local/season/{series_title}/{season_number}"
        episodes = tuple(
            EpisodeRef(source_url=f"{base}/e/{n}", number=n)
            for n in range(1, self._episode_count + 1)
        )
        return SeasonDiscovery(
            series_title=series_title,
            season_number=season_number,
            release_year=self._release_year,
            episodes=episodes,
        )

    def resolve_media(self, episode: EpisodeRef) -> MediaLocator:
        return MediaLocator(
            url=f"https://fake.local/media/{episode.number}.mp4",
            suggested_filename=f"E{episode.number:02d}.mp4",
        )

    def next_episode(self, episode: EpisodeRef) -> EpisodeRef | None:
        series_title, season_number = _parse_episode(episode)
        next_num = episode.number + 1
        if next_num > self._episode_count:
            return None
        base = f"https://fake.local/season/{series_title}/{season_number}"
        return EpisodeRef(source_url=f"{base}/e/{next_num}", number=next_num)


def _parse(url: SourceUrl) -> tuple[str, int]:
    parsed = urlparse(url.value)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 3 or parts[0] != "season":
        raise ValueError(f"Not a fake season URL: {url.value!r}")
    return parts[1], int(parts[2])


def _parse_episode(episode: EpisodeRef) -> tuple[str, int]:
    parsed = urlparse(episode.source_url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 4 or parts[0] != "season" or parts[3] != "e":
        raise ValueError(f"Not a fake episode URL: {episode.source_url!r}")
    return parts[1], int(parts[2])
