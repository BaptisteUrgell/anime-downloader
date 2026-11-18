from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from anime_downloader.domain.model import Episode, EpisodeStatus, Season, Series
from anime_downloader.infrastructure.db.models import EpisodeRow, SeasonRow, SeriesRow


class SqlAlchemyLibraryRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def upsert_series(self, series: Series) -> Series:
        with self._session_factory() as session:
            row = session.get(SeriesRow, series.id)
            if row is not None:
                row.title = series.title
            else:
                row = session.scalar(
                    select(SeriesRow).where(SeriesRow.title == series.title)
                )
                if row is None:
                    row = SeriesRow(id=series.id, title=series.title)
                    session.add(row)
            session.commit()
            return _to_series(row)

    def upsert_season(self, season: Season) -> Season:
        with self._session_factory() as session:
            row = session.get(SeasonRow, season.id)
            if row is not None:
                row.series_id = season.series_id
                row.number = season.number
            else:
                row = session.scalar(
                    select(SeasonRow).where(
                        SeasonRow.series_id == season.series_id,
                        SeasonRow.number == season.number,
                    )
                )
                if row is None:
                    row = SeasonRow(
                        id=season.id,
                        series_id=season.series_id,
                        number=season.number,
                    )
                    session.add(row)
            session.commit()
            return _to_season(row)

    def upsert_episode(self, episode: Episode) -> Episode:
        with self._session_factory() as session:
            row = session.get(EpisodeRow, episode.id)
            if row is None:
                row = session.scalar(
                    select(EpisodeRow).where(
                        EpisodeRow.season_id == episode.season_id,
                        EpisodeRow.number == episode.number,
                    )
                )
            if row is not None:
                row.season_id = episode.season_id
                row.number = episode.number
                row.title = episode.title
                row.status = episode.status.value
                row.source_url = episode.source_url
                row.file_path = episode.file_path
                row.error_message = episode.error_message
            else:
                row = EpisodeRow(
                    id=episode.id,
                    season_id=episode.season_id,
                    number=episode.number,
                    title=episode.title,
                    status=episode.status.value,
                    source_url=episode.source_url,
                    file_path=episode.file_path,
                    error_message=episode.error_message,
                )
                session.add(row)
            session.commit()
            return _to_episode(row)

    def list_series(self) -> list[Series]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(SeriesRow).order_by(SeriesRow.title.asc(), SeriesRow.id.asc())
            ).all()
            return [_to_series(row) for row in rows]

    def list_seasons(self, series_id: str) -> list[Season]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(SeasonRow)
                .where(SeasonRow.series_id == series_id)
                .order_by(SeasonRow.number.asc(), SeasonRow.id.asc())
            ).all()
            return [_to_season(row) for row in rows]

    def list_episodes(self, season_id: str) -> list[Episode]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(EpisodeRow)
                .where(EpisodeRow.season_id == season_id)
                .order_by(EpisodeRow.number.asc(), EpisodeRow.id.asc())
            ).all()
            return [_to_episode(row) for row in rows]

    def get_episode(self, episode_id: str) -> Episode | None:
        with self._session_factory() as session:
            row = session.get(EpisodeRow, episode_id)
            return _to_episode(row) if row is not None else None

    def list_failed_episodes(self, season_id: str) -> list[Episode]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(EpisodeRow)
                .where(
                    EpisodeRow.season_id == season_id,
                    EpisodeRow.status == EpisodeStatus.FAILED.value,
                )
                .order_by(EpisodeRow.number.asc(), EpisodeRow.id.asc())
            ).all()
            return [_to_episode(row) for row in rows]


def _to_series(row: SeriesRow) -> Series:
    return Series(id=row.id, title=row.title)


def _to_season(row: SeasonRow) -> Season:
    return Season(id=row.id, series_id=row.series_id, number=row.number)


def _to_episode(row: EpisodeRow) -> Episode:
    return Episode(
        id=row.id,
        season_id=row.season_id,
        number=row.number,
        title=row.title,
        status=EpisodeStatus(row.status),
        source_url=row.source_url,
        file_path=row.file_path,
        error_message=row.error_message,
    )
