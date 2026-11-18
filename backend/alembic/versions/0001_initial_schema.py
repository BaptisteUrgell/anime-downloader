"""Initial schema for series, seasons, episodes, and jobs.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("title"),
    )

    op.create_table(
        "seasons",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "number", name="uq_seasons_series_number"),
    )
    op.create_index(op.f("ix_seasons_series_id"), "seasons", ["series_id"], unique=False)

    op.create_table(
        "episodes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("season_id", sa.String(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "number", name="uq_episodes_season_number"),
    )
    op.create_index(
        op.f("ix_episodes_season_id"), "episodes", ["season_id"], unique=False
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("adapter_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=True),
        sa.Column("season_id", sa.String(), nullable=True),
        sa.Column("total_episodes", sa.Integer(), nullable=False),
        sa.Column("completed_episodes", sa.Integer(), nullable=False),
        sa.Column("failed_episodes", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_episodes_season_id"), table_name="episodes")
    op.drop_table("episodes")
    op.drop_index(op.f("ix_seasons_series_id"), table_name="seasons")
    op.drop_table("seasons")
    op.drop_table("series")
