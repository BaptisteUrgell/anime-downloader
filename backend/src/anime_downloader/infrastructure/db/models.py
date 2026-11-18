from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from anime_downloader.infrastructure.db.base import Base


class SeriesRow(Base):
    __tablename__ = "series"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False, unique=True)


class SeasonRow(Base):
    __tablename__ = "seasons"
    __table_args__ = (
        UniqueConstraint("series_id", "number", name="uq_seasons_series_number"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    series_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("series.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)


class EpisodeRow(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("season_id", "number", name="uq_episodes_season_number"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    season_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("seasons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    adapter_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    series_id: Mapped[str | None] = mapped_column(String, nullable=True)
    season_id: Mapped[str | None] = mapped_column(String, nullable=True)
    total_episodes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_episodes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_episodes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    dismissed_at: Mapped[str | None] = mapped_column(String, nullable=True)
