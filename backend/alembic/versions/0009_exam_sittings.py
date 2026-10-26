"""exam papers: a sitting, regular or ODEL

ODEL and part-time students sit papers of their own: a unit can have a
regular paper and an ODEL paper, each sat by its own class rows. Smart
Attendance sends each paper's sitting; it is shown with the codes
("MATH 241 (ODEL)") and passed on to SMARTTT.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-26 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("exam_papers") as batch:
        batch.add_column(sa.Column("sitting", sa.String(10), nullable=False, server_default="regular"))


def downgrade() -> None:
    with op.batch_alter_table("exam_papers") as batch:
        batch.drop_column("sitting")
