"""initial generator tables

Revision ID: 0001
Revises:
Create Date: 2026-10-18 21:29:45.586901
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_account_id", sa.String(length=64), nullable=False),
        sa.Column("actor_name", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_entity", "audit_log", ["entity", "entity_id"], unique=False)
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("identity", sa.JSON(), nullable=False),
        sa.Column("identity_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_auth_sessions_account_id"), "auth_sessions", ["account_id"], unique=False)
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_attempt_key_at", "login_attempts", ["key", "at"], unique=False)
    op.create_table(
        "terms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("smarttt_term_id", sa.String(length=64), nullable=False),
        sa.Column("academic_year", sa.String(length=20), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("smarttt_term_id"),
    )
    op.create_table(
        "class_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("smarttt_program_id", sa.Integer(), nullable=False),
        sa.Column("program_code", sa.String(length=64), nullable=False),
        sa.Column("study_year", sa.Integer(), nullable=False),
        sa.Column("study_semester", sa.Integer(), nullable=False),
        sa.Column("sub_class", sa.String(length=10), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("student_count", sa.Integer(), nullable=True),
        sa.Column("unavailable", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "term_id", "smarttt_program_id", "study_year", "study_semester", "sub_class", name="uq_class_row"
        ),
    )
    op.create_index(op.f("ix_class_rows_term_id"), "class_rows", ["term_id"], unique=False)
    op.create_table(
        "drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("parent_draft_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.Enum("draft", "published", "superseded", name="draft_status"), nullable=False),
        sa.Column("soft_scores", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_drafts_term_id"), "drafts", ["term_id"], unique=False)
    op.create_table(
        "snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_snapshots_term_id"), "snapshots", ["term_id"], unique=False)
    op.create_table(
        "unit_offerings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("smarttt_unit_id", sa.Integer(), nullable=False),
        sa.Column("unit_code", sa.String(length=64), nullable=False),
        sa.Column("unit_name", sa.String(length=255), nullable=False),
        sa.Column("owning_department_id", sa.Integer(), nullable=False),
        sa.Column("weekly_hours", sa.Integer(), nullable=True),
        sa.Column("session_length", sa.Integer(), nullable=True),
        sa.Column("room_type", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term_id", "smarttt_unit_id", name="uq_offering_unit"),
    )
    op.create_index(op.f("ix_unit_offerings_term_id"), "unit_offerings", ["term_id"], unique=False)
    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("offering_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["offering_id"], ["unit_offerings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offering_id", "label", name="uq_group_label"),
    )
    op.create_index(op.f("ix_groups_offering_id"), "groups", ["offering_id"], unique=False)
    op.create_table(
        "offering_class_rows",
        sa.Column("offering_id", sa.Uuid(), nullable=False),
        sa.Column("class_row_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["class_row_id"], ["class_rows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offering_id"], ["unit_offerings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("offering_id", "class_row_id"),
    )
    op.create_table(
        "publications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("published_by", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("smarttt_response", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term_id", "version", name="uq_publication_version"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.Enum("full", "resolve", "repair", name="run_mode"), nullable=False),
        sa.Column("base_draft_id", sa.Uuid(), nullable=True),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("time_limit_s", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("queued", "running", "succeeded", "failed", name="run_status"), nullable=False),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("soft_scores", sa.JSON(), nullable=False),
        sa.Column("solve_seconds", sa.Float(), nullable=True),
        sa.Column("failure", sa.JSON(), nullable=True),
        sa.Column("result_draft_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["base_draft_id"], ["drafts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_term_created", "runs", ["term_id", "created_at"], unique=False)
    op.create_table(
        "draft_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("smarttt_room_id", sa.String(length=64), nullable=False),
        sa.Column("start_slot", sa.Integer(), nullable=False),
        sa.Column("length", sa.Integer(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draft_id", "key", name="uq_draft_session_key"),
    )
    op.create_index(op.f("ix_draft_sessions_draft_id"), "draft_sessions", ["draft_id"], unique=False)
    op.create_table(
        "group_class_rows",
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("class_row_id", sa.Uuid(), nullable=False),
        sa.Column("students", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["class_row_id"], ["class_rows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("group_id", "class_row_id"),
    )


def downgrade() -> None:
    op.drop_table("group_class_rows")
    op.drop_index(op.f("ix_draft_sessions_draft_id"), table_name="draft_sessions")
    op.drop_table("draft_sessions")
    op.drop_index("ix_runs_term_created", table_name="runs")
    op.drop_table("runs")
    op.drop_table("publications")
    op.drop_table("offering_class_rows")
    op.drop_index(op.f("ix_groups_offering_id"), table_name="groups")
    op.drop_table("groups")
    op.drop_index(op.f("ix_unit_offerings_term_id"), table_name="unit_offerings")
    op.drop_table("unit_offerings")
    op.drop_index(op.f("ix_snapshots_term_id"), table_name="snapshots")
    op.drop_table("snapshots")
    op.drop_index(op.f("ix_drafts_term_id"), table_name="drafts")
    op.drop_table("drafts")
    op.drop_index(op.f("ix_class_rows_term_id"), table_name="class_rows")
    op.drop_table("class_rows")
    op.drop_table("terms")
    op.drop_index("ix_login_attempt_key_at", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_index(op.f("ix_auth_sessions_account_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_audit_entity", table_name="audit_log")
    op.drop_table("audit_log")
    for name in ("draft_status", "run_status", "run_mode"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
