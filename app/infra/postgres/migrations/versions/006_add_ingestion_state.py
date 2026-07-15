"""Add ingestion pipeline table/remove extra attrs from stations

Revision ID: 006_add_ingestion_state
Revises: 005_add_description
Create Date: 2026-07-15 11:11:54.988797

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_add_ingestion_state"
down_revision: Union[str, Sequence[str], None] = "005_add_description"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ingestion_pipeline_states",
        sa.Column("station_id", sa.String(), nullable=False),
        sa.Column("pipeline_type", sa.String(), nullable=False),
        sa.Column("last_processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_sec", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("claimed_by", sa.String(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
        ),
        sa.PrimaryKeyConstraint("station_id", "pipeline_type", name="ingestion_pipeline_states_pk"),
    )
    op.drop_column("stations", "fetch_error")
    op.drop_column("stations", "claimed_by")
    op.drop_column("stations", "lease_until")
    op.drop_column("stations", "priority")
    op.drop_column("stations", "last_fetched_at")
    op.drop_column("stations", "next_fetch_at")
    op.drop_column("stations", "fetch_interval_sec")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("stations", sa.Column("fetch_interval_sec", sa.INTEGER(), autoincrement=False, nullable=False))
    op.add_column(
        "stations", sa.Column("next_fetch_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False)
    )
    op.add_column(
        "stations",
        sa.Column("last_fetched_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    )
    op.add_column("stations", sa.Column("priority", sa.INTEGER(), autoincrement=False, nullable=False))
    op.add_column(
        "stations", sa.Column("lease_until", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True)
    )
    op.add_column("stations", sa.Column("claimed_by", sa.VARCHAR(), autoincrement=False, nullable=True))
    op.add_column("stations", sa.Column("fetch_error", sa.VARCHAR(), autoincrement=False, nullable=True))
    op.drop_table("ingestion_pipeline_states")
