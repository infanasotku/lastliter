"""Add field to station table for ingestion loop

Revision ID: 002_add_fields_to_station
Revises: 001_add_station_table
Create Date: 2026-07-04 22:44:12.404815

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_add_fields_to_station"
down_revision: Union[str, Sequence[str], None] = "001_add_station_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("stations", sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE stations SET last_fetched_at = '-infinity'::timestamptz")
    op.alter_column("stations", "last_fetched_at", nullable=False)

    op.add_column("stations", sa.Column("next_fetch_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE stations SET next_fetch_at = NOW()")
    op.alter_column("stations", "next_fetch_at", nullable=False)

    op.add_column("stations", sa.Column("fetch_interval_sec", sa.Integer(), nullable=True))
    op.execute("UPDATE stations SET fetch_interval_sec = 0")
    op.alter_column("stations", "fetch_interval_sec", nullable=False)

    op.add_column("stations", sa.Column("priority", sa.Integer(), nullable=True))
    op.execute("UPDATE stations SET priority = 0")
    op.alter_column("stations", "priority", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stations", "priority")
    op.drop_column("stations", "fetch_interval_sec")
    op.drop_column("stations", "next_fetch_at")
    op.drop_column("stations", "last_fetched_at")
