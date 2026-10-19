"""master data entry: lecture halls, departments, term details, local class rows and units

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("school", sa.String(length=255), nullable=False),
        sa.Column("lecturer_count", sa.Integer(), nullable=True),
        sa.Column("smarttt_department_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("smarttt_department_id"),
    )
    op.create_table(
        "rooms",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("building", sa.String(length=120), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("room_type", sa.String(length=30), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("unavailable", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    with op.batch_alter_table("terms") as batch:
        batch.alter_column("smarttt_term_id", existing_type=sa.String(length=64), nullable=True)
        batch.add_column(sa.Column("name", sa.String(length=120), nullable=False, server_default=""))
        batch.add_column(sa.Column("start_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("end_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("version_label", sa.String(length=120), nullable=False, server_default=""))
        batch.add_column(sa.Column("use_from", sa.Date(), nullable=True))
        batch.add_column(sa.Column("prepared_by", sa.String(length=255), nullable=False, server_default=""))
        batch.add_column(
            sa.Column(
                "prepared_by_title",
                sa.String(length=255),
                nullable=False,
                server_default="Director Examination & Timetabling",
            )
        )
        batch.add_column(sa.Column("default_session_length", sa.Integer(), nullable=False, server_default="3"))
    with op.batch_alter_table("class_rows") as batch:
        batch.alter_column("smarttt_program_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("department_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("unit_offerings") as batch:
        batch.alter_column("smarttt_unit_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("unit_offerings") as batch:
        batch.alter_column("smarttt_unit_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("class_rows") as batch:
        batch.drop_column("department_id")
        batch.alter_column("smarttt_program_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("terms") as batch:
        for column in (
            "default_session_length",
            "prepared_by_title",
            "prepared_by",
            "use_from",
            "version_label",
            "end_date",
            "start_date",
            "name",
        ):
            batch.drop_column(column)
        batch.alter_column("smarttt_term_id", existing_type=sa.String(length=64), nullable=False)
    op.drop_table("rooms")
    op.drop_table("departments")
