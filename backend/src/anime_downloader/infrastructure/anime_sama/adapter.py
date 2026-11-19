from __future__ import annotations

import re
from urllib.parse import urlparse

from anime_downloader.domain.model import EpisodeRef, MediaLocator, SeasonDiscovery, SourceUrl
from anime_downloader.infrastructure.anime_sama.provider import AnimeSamaProvider

_SAISON_RE = re.compile(r"^saison(\d+)$", re.IGNORECASE)


class AnimeSamaAdapter:
    def __init__(self, provider: AnimeSamaProvider | None = None) -> None:
        self._provider = provider or AnimeSamaProvider()

    @property
    def adapter_id(self) -> str:
        return "anime-sama"

    def matches(self, url: SourceUrl) -> bool:
        return self._provider.matches(url.value)

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        episodes = self._provider.discover_season(url.value)
        slug, season_number = _parse_slug_and_season(url.value)
        title, year = self._provider.fetch_oeuvre_meta(_oeuvre_url(url.value, slug))
        return SeasonDiscovery(
            series_title=title,
            release_year=year,
            season_number=season_number,
            episodes=tuple(
                EpisodeRef(source_url=url.value, number=ep.number, title=ep.title)
                for ep in episodes
            ),
        )

    def resolve_media(self, episode: EpisodeRef) -> MediaLocator:
        media = self._provider.resolve_media_for_episode(
            episode.source_url, episode.number
        )
        return MediaLocator(url=media.url, headers=dict(media.headers))

    def next_episode(self, episode: EpisodeRef) -> EpisodeRef | None:
        season_url = episode.source_url
        cache = self._provider.get_cached_season(season_url)
        if cache is None:
            self._provider.discover_season(season_url)
            cache = self._provider.get_cached_season(season_url)
        if cache is None:
            return None

        for ep in cache.episodes:
            if ep.number == episode.number + 1:
                return EpisodeRef(
                    source_url=season_url,
                    number=ep.number,
                    title=ep.title,
                )
        return None


def _parse_slug_and_season(season_url: str) -> tuple[str, int]:
    parsed = urlparse(season_url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 3 or parts[0].lower() != "catalogue":
        raise ValueError(f"Not an anime-sama season URL: {season_url!r}")

    slug = parts[1]
    season_match = _SAISON_RE.match(parts[2])
    if season_match is None:
        raise ValueError(f"Cannot parse season number from URL: {season_url!r}")

    return slug, int(season_match.group(1))


def _oeuvre_url(season_url: str, slug: str) -> str:
    parsed = urlparse(season_url)
    return f"{parsed.scheme}://{parsed.netloc}/catalogue/{slug}/"
