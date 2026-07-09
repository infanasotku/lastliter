"""Add fetch_error to stations

Revision ID: 004_add_fetch_error
Revises: 003_add_lease_attrs
Create Date: 2026-07-09 20:34:13.240408

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_add_fetch_error"
down_revision: Union[str, Sequence[str], None] = "003_add_lease_attrs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("stations", sa.Column("fetch_error", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stations", "fetch_error")
