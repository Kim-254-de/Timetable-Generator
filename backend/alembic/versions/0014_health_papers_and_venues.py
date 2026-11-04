"""Papers the Director uploads (with the invigilators they name), and venues they choose on a draft

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("exam_placements") as batch:
        batch.add_column(sa.Column("rooms_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("exam_papers") as batch:
        batch.add_column(sa.Column("director_invigilators", sa.JSON(), nullable=False, server_default="{}"))
    with op.batch_alter_table("exam_paper_rows") as batch:
        batch.add_column(sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("exam_paper_rows") as batch:
        batch.drop_column("edited")
    with op.batch_alter_table("exam_papers") as batch:
        batch.drop_column("director_invigilators")
    with op.batch_alter_table("exam_placements") as batch:
        batch.drop_column("rooms_locked")
