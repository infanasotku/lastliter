"""Init empty migrations

Revision ID: 000_init_migrations
Revises:
Create Date: 2026-07-04 13:59:54.455526

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "000_init_migrations"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
