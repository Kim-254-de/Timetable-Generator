"""switching SMARTTT from teaching to exams: the switch and the close of the exam period

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-24 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    ("exam_switch_at", sa.DateTime(timezone=True)),
    ("exam_switched_at", sa.DateTime(timezone=True)),
    ("exam_switched_by", sa.String(length=255)),
    ("exam_close_at", sa.DateTime(timezone=True)),
    ("exam_closed_at", sa.DateTime(timezone=True)),
    ("exam_closed_by", sa.String(length=255)),
)


def upgrade() -> None:
    with op.batch_alter_table("terms") as batch:
        for name, kind in COLUMNS:
            batch.add_column(sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("terms") as batch:
        for name, _kind in reversed(COLUMNS):
            batch.drop_column(name)
