from __future__ import annotations

from urllib.parse import urlparse

from anime_downloader.domain.model import EpisodeRef, MediaLocator, SeasonDiscovery, SourceUrl


class DemoAdapter:
    def __init__(self, episode_count: int = 3) -> None:
        self._episode_count = episode_count

    @property
    def adapter_id(self) -> str:
        return "demo"

    def matches(self, url: SourceUrl) -> bool:
        parsed = urlparse(url.value)
        if parsed.netloc.lower() != "demo.local":
            return False
        return parsed.path.startswith("/season/")

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        series_title, season_number = _parse_season_path(url)
        base = f"https://demo.local/season/{series_title}/{season_number}"
        episodes = tuple(
            EpisodeRef(source_url=f"{base}/e/{n}", number=n)
            for n in range(1, self._episode_count + 1)
        )
        return SeasonDiscovery(
            series_title=series_title,
            season_number=season_number,
            episodes=episodes,
        )

    def resolve_media(self, episode: EpisodeRef) -> MediaLocator:
        n = episode.number
        return MediaLocator(
            url=f"https://demo.local/media/{n}.mp4",
            suggested_filename=f"E{n:02d}.mp4",
        )

    def next_episode(self, episode: EpisodeRef) -> EpisodeRef | None:
        series_title, season_number = _parse_season_path_from_episode(episode)
        next_num = episode.number + 1
        if next_num > self._episode_count:
            return None
        base = f"https://demo.local/season/{series_title}/{season_number}"
        return EpisodeRef(source_url=f"{base}/e/{next_num}", number=next_num)


def _parse_season_path(url: SourceUrl) -> tuple[str, int]:
    parsed = urlparse(url.value)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 3 or parts[0] != "season":
        raise ValueError(f"Not a demo season URL: {url.value!r}")
    return parts[1], int(parts[2])


def _parse_season_path_from_episode(episode: EpisodeRef) -> tuple[str, int]:
    parsed = urlparse(episode.source_url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 4 or parts[0] != "season" or parts[3] != "e":
        raise ValueError(f"Not a demo episode URL: {episode.source_url!r}")
    return parts[1], int(parts[2])