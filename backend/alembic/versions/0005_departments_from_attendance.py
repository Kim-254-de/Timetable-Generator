"""departments come from Smart Attendance: link each to Attendance's department

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("departments", sa.Column("attendance_department_id", sa.String(length=64), nullable=True))
    op.add_column("departments", sa.Column("attendance_lecturer_count", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_departments_attendance_id", "departments", ["attendance_department_id"])


def downgrade() -> None:
    op.drop_constraint("uq_departments_attendance_id", "departments", type_="unique")
    op.drop_column("departments", "attendance_lecturer_count")
    op.drop_column("departments", "attendance_department_id")
