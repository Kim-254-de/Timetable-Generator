"""Paper categories and health rooms; the administrator's and Director's say on a room's exam use.

Rooms the Director already kept out of exams stay out: that choice moves to exam_override,
and for_exams becomes the administrator's say, read from SMARTTT.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.add_column(sa.Column("exam_override", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("health_unit", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(
        sa.text("UPDATE rooms SET exam_override = :no, for_exams = :yes WHERE for_exams = :no").bindparams(
            no=False, yes=True
        )
    )
    with op.batch_alter_table("terms") as batch:
        batch.add_column(sa.Column("exam_health_prefixes", sa.JSON(), nullable=False, server_default="[]"))
    with op.batch_alter_table("exam_papers") as batch:
        batch.add_column(sa.Column("category_override", sa.String(20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("exam_papers") as batch:
        batch.drop_column("category_override")
    with op.batch_alter_table("terms") as batch:
        batch.drop_column("exam_health_prefixes")
    op.execute(sa.text("UPDATE rooms SET for_exams = :no WHERE exam_override = :no").bindparams(no=False))
    with op.batch_alter_table("rooms") as batch:
        batch.drop_column("health_unit")
        batch.drop_column("exam_override")
