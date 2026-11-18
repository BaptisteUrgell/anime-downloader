"""Add jobs.dismissed_at for soft-delete.

Revision ID: 0002_jobs_dismissed_at
Revises: 0001_initial_schema
Create Date: 2026-11-18 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_jobs_dismissed_at"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("dismissed_at", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "dismissed_at")