"""keep each approved version as approved: the payload sent to SMARTTT and the classes as shown

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("publications", sa.Column("payload", sa.JSON(), nullable=True))
    op.add_column("publications", sa.Column("record", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("publications", "record")
    op.drop_column("publications", "payload")
