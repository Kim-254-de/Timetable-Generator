"""departments' teaching imported from the Allocator: refs, group lecturers, imports, keep-published re-solves

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("class_rows") as batch:
        batch.add_column(sa.Column("allocator_ref", sa.String(length=64), nullable=True))
        batch.create_index("ix_class_rows_allocator_ref", ["allocator_ref"], unique=True)
    with op.batch_alter_table("unit_offerings") as batch:
        batch.add_column(sa.Column("allocator_ref", sa.String(length=64), nullable=True))
        batch.create_index("ix_unit_offerings_allocator_ref", ["allocator_ref"], unique=True)
    with op.batch_alter_table("groups") as batch:
        batch.add_column(sa.Column("allocator_ref", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("lecturer_staff_number", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("lecturer_name", sa.String(length=255), nullable=False, server_default=""))
        batch.add_column(sa.Column("lecture_hours", sa.Float(), nullable=True))
        batch.add_column(sa.Column("practical_hours", sa.Float(), nullable=True))
        batch.add_column(sa.Column("cf_hours", sa.Float(), nullable=True))
        batch.create_index("ix_groups_allocator_ref", ["allocator_ref"], unique=True)
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("keep_published", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "department_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("department_code", sa.String(length=32), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_by", sa.String(length=255), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term_id", "department_code", name="uq_department_import"),
    )
    op.create_index("ix_department_imports_term_id", "department_imports", ["term_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_department_imports_term_id", table_name="department_imports")
    op.drop_table("department_imports")
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("keep_published")
    with op.batch_alter_table("groups") as batch:
        batch.drop_index("ix_groups_allocator_ref")
        batch.drop_column("cf_hours")
        batch.drop_column("practical_hours")
        batch.drop_column("lecture_hours")
        batch.drop_column("lecturer_name")
        batch.drop_column("lecturer_staff_number")
        batch.drop_column("allocator_ref")
    with op.batch_alter_table("unit_offerings") as batch:
        batch.drop_index("ix_unit_offerings_allocator_ref")
        batch.drop_column("allocator_ref")
    with op.batch_alter_table("class_rows") as batch:
        batch.drop_index("ix_class_rows_allocator_ref")
        batch.drop_column("allocator_ref")
