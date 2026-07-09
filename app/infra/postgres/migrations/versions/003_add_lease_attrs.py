"""Add lease attributes to stations

Revision ID: 003_add_lease_attrs
Revises: 002_add_fields_to_station
Create Date: 2026-07-09 20:01:46.938838

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_lease_attrs"
down_revision: Union[str, Sequence[str], None] = "002_add_fields_to_station"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("stations", sa.Column("claimed_by", sa.String(), nullable=True))
    op.add_column("stations", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stations", "lease_until")
    op.drop_column("stations", "claimed_by")
