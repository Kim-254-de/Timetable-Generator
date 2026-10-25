"""departments: no school (faculty); the code can come from Smart Attendance

Faculties play no part any more. An administrator creates each department in
Smart Attendance with a name and a code; the Generator takes both from there
and marks a code that came from Attendance, which can only be changed there.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-24 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("departments") as batch:
        batch.drop_column("school")
        batch.add_column(sa.Column("code_from_attendance", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("departments") as batch:
        batch.drop_column("code_from_attendance")
        batch.add_column(sa.Column("school", sa.String(length=255), nullable=False, server_default=""))
