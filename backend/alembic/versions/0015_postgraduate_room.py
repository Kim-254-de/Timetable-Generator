"""The room a term's postgraduate papers sit in first ("TC 1"); they overflow into its building

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("terms") as batch:
        batch.add_column(sa.Column("exam_postgraduate_room", sa.String(30), nullable=False, server_default="TC 1"))


def downgrade() -> None:
    with op.batch_alter_table("terms") as batch:
        batch.drop_column("exam_postgraduate_room")
