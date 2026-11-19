"""Add series.release_year; unique (title, release_year).

Revision ID: 0003_series_release_year
Revises: 0002_jobs_dismissed_at
Create Date: 2026-11-19 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_series_release_year"
down_revision: str | None = "0002_jobs_dismissed_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 0001 emitted UNIQUE (title) with no name. Reflection reports that
# constraint as unnamed; this convention assigns uq_series_title so
# batch mode can drop it. Downgrade recreates the constraint as "title",
# so upgrade drops whichever name is actually present.
_SQLITE_UNIQUE_NAMING = {
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}
_UNNAMED_TITLE_UNIQUE = "uq_series_title"


def _title_unique_constraint_name() -> str:
    constraints = sa.inspect(op.get_bind()).get_unique_constraints("series")
    for constraint in constraints:
        if constraint.get("column_names") == ["title"]:
            name = constraint.get("name")
            return _UNNAMED_TITLE_UNIQUE if name is None else str(name)
    return _UNNAMED_TITLE_UNIQUE


def upgrade() -> None:
    with op.batch_alter_table(
        "series",
        naming_convention=_SQLITE_UNIQUE_NAMING,
    ) as batch:
        batch.add_column(sa.Column("release_year", sa.Integer(), nullable=True))
        batch.drop_constraint(_title_unique_constraint_name(), type_="unique")
        batch.create_unique_constraint(
            "uq_series_title_release_year", ["title", "release_year"]
        )


def downgrade() -> None:
    with op.batch_alter_table("series") as batch:
        batch.drop_constraint("uq_series_title_release_year", type_="unique")
        batch.create_unique_constraint("title", ["title"])
        batch.drop_column("release_year")
