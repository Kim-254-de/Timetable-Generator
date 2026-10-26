"""exam papers: the main invigilator a department named before generating

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-27 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("exam_papers") as batch:
        batch.add_column(sa.Column("invigilator_staff_number", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("exam_papers") as batch:
        batch.drop_column("invigilator_staff_number")
