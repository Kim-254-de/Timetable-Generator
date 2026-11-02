"""exam paper rows: a class guessed from the paper's code takes seats, but no hard rule holds it

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-03 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("exam_paper_rows") as batch:
        batch.add_column(sa.Column("guessed", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("exam_paper_rows") as batch:
        batch.drop_column("guessed")
