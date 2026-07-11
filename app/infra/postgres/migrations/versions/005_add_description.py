"""Add description to station

Revision ID: 005_add_description
Revises: 004_add_fetch_error
Create Date: 2026-07-11 15:30:26.792340

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_add_description"
down_revision: Union[str, Sequence[str], None] = "004_add_fetch_error"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("stations", sa.Column("description", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stations", "description")
