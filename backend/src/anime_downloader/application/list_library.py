from __future__ import annotations

from dataclasses import dataclass

from anime_downloader.domain.model import Episode
from anime_downloader.domain.ports import LibraryRepository


@dataclass(frozen=True)
class LibrarySeason:
    id: str
    series_id: str
    number: int
    episodes: list[Episode]


@dataclass(frozen=True)
class LibrarySeries:
    id: str
    title: str
    seasons: list[LibrarySeason]


def list_library(library: LibraryRepository) -> list[LibrarySeries]:
    result: list[LibrarySeries] = []
    for series in library.list_series():
        seasons = [
            LibrarySeason(
                id=season.id,
                series_id=season.series_id,
                number=season.number,
                episodes=library.list_episodes(season.id),
            )
            for season in library.list_seasons(series.id)
        ]
        result.append(
            LibrarySeries(
                id=series.id,
                title=series.title,
                seasons=seasons,
            )
        )
    return result
