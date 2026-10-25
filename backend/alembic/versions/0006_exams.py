"""exams: exam period, room exam seats, papers, practicals, drafts, seating and versions

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-23 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_SESSIONS = (
    '[{"start": "08:30", "end": "10:30"}, {"start": "11:30", "end": "13:30"}, {"start": "14:30", "end": "16:30"}]'
)


def _draft_status() -> sa.types.TypeEngine[str]:
    """The existing draft_status type (exam drafts share it), never created again."""
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM("draft", "published", "superseded", name="draft_status", create_type=False)
    return sa.Enum("draft", "published", "superseded", name="draft_status")


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE run_mode ADD VALUE IF NOT EXISTS 'exam'")
    with op.batch_alter_table("terms") as batch:
        batch.add_column(sa.Column("exam_start", sa.Date(), nullable=True))
        batch.add_column(sa.Column("exam_end", sa.Date(), nullable=True))
        batch.add_column(sa.Column("exam_weekdays", sa.JSON(), nullable=False, server_default="[0, 1, 2, 3, 4]"))
        batch.add_column(sa.Column("exam_days_off", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("exam_sessions", sa.JSON(), nullable=False, server_default=DEFAULT_SESSIONS))
        batch.add_column(sa.Column("exam_spacing", sa.Float(), nullable=False, server_default="0.9"))
    with op.batch_alter_table("rooms") as batch:
        batch.add_column(sa.Column("exam_seats", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("for_exams", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("exam_base_id", sa.Uuid(), nullable=True))

    op.create_table(
        "exam_papers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("allocator_ref", sa.String(length=64), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("codes", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("examiner_staff_number", sa.String(length=64), nullable=True),
        sa.Column("examiner_name", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exam_paper_term", "exam_papers", ["term_id"], unique=False)
    op.create_index("ix_exam_papers_allocator_ref", "exam_papers", ["allocator_ref"], unique=True)
    op.create_table(
        "exam_paper_rows",
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("class_row_id", sa.Uuid(), nullable=False),
        sa.Column("students", sa.Integer(), nullable=False),
        sa.Column("odel", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["class_row_id"], ["class_rows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_id"], ["exam_papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_id", "class_row_id"),
    )
    op.create_table(
        "exam_practicals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("allocator_ref", sa.String(length=64), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("codes", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.String(length=5), nullable=False),
        sa.Column("end_time", sa.String(length=5), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exam_practicals_term_id", "exam_practicals", ["term_id"], unique=False)
    op.create_index("ix_exam_practicals_allocator_ref", "exam_practicals", ["allocator_ref"], unique=True)
    op.create_table(
        "exam_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", _draft_status(), nullable=False),
        sa.Column("soft_scores", sa.JSON(), nullable=False),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exam_drafts_term_id", "exam_drafts", ["term_id"], unique=False)
    op.create_table(
        "exam_placements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("session", sa.Integer(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["exam_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_id"], ["exam_papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draft_id", "paper_id", name="uq_exam_placement_paper"),
    )
    op.create_index("ix_exam_placements_draft_id", "exam_placements", ["draft_id"], unique=False)
    op.create_table(
        "exam_seats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("placement_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.String(length=64), nullable=False),
        sa.Column("class_row_id", sa.Uuid(), nullable=False),
        sa.Column("part", sa.Integer(), nullable=False),
        sa.Column("parts", sa.Integer(), nullable=False),
        sa.Column("students", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["placement_id"], ["exam_placements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exam_seats_placement_id", "exam_seats", ["placement_id"], unique=False)
    op.create_table(
        "exam_publications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("published_by", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("smarttt_response", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("record", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["exam_drafts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term_id", "version", name="uq_exam_publication_version"),
    )


def downgrade() -> None:
    op.drop_table("exam_publications")
    op.drop_index("ix_exam_seats_placement_id", table_name="exam_seats")
    op.drop_table("exam_seats")
    op.drop_index("ix_exam_placements_draft_id", table_name="exam_placements")
    op.drop_table("exam_placements")
    op.drop_index("ix_exam_drafts_term_id", table_name="exam_drafts")
    op.drop_table("exam_drafts")
    op.drop_index("ix_exam_practicals_allocator_ref", table_name="exam_practicals")
    op.drop_index("ix_exam_practicals_term_id", table_name="exam_practicals")
    op.drop_table("exam_practicals")
    op.drop_table("exam_paper_rows")
    op.drop_index("ix_exam_papers_allocator_ref", table_name="exam_papers")
    op.drop_index("ix_exam_paper_term", table_name="exam_papers")
    op.drop_table("exam_papers")
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("exam_base_id")
    with op.batch_alter_table("rooms") as batch:
        batch.drop_column("for_exams")
        batch.drop_column("exam_seats")
    with op.batch_alter_table("terms") as batch:
        batch.drop_column("exam_spacing")
        batch.drop_column("exam_sessions")
        batch.drop_column("exam_days_off")
        batch.drop_column("exam_weekdays")
        batch.drop_column("exam_end")
        batch.drop_column("exam_start")
    # PostgreSQL can't drop a value from an enum type; 'exam' stays in run_mode, unused.
