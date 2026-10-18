"""
The Generator's own data (handoff 5.8): the term being built, snapshots of
SMARTTT's master data, class rows, unit offerings and their groups, solver
runs, drafts and their sessions, publications, the audit trail, and sign-in
sessions. Master data itself (rooms, units, programmes, lecturers) stays in
SMARTTT and is only copied here inside snapshots.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class RunMode(enum.StrEnum):
    FULL = "full"  # solve the whole term from scratch
    RESOLVE = "resolve"  # re-solve a draft around the Director's pinned sessions
    REPAIR = "repair"  # mid-term change: keep the published timetable where possible (S8, H13)


class RunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DraftStatus(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"  # a later version was published


class Term(Base):
    __tablename__ = "terms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    smarttt_term_id: Mapped[str] = mapped_column(String(64), unique=True)
    academic_year: Mapped[str] = mapped_column(String(20))
    semester: Mapped[int] = mapped_column(Integer)  # calendar term 1-3; May-August is 3
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClassRow(Base):
    """A cohort as printed on the timetable: programme + year + study semester (+ sub-class)."""

    __tablename__ = "class_rows"
    __table_args__ = (
        UniqueConstraint(
            "term_id", "smarttt_program_id", "study_year", "study_semester", "sub_class", name="uq_class_row"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    smarttt_program_id: Mapped[int] = mapped_column(Integer)
    program_code: Mapped[str] = mapped_column(String(64))
    study_year: Mapped[int] = mapped_column(Integer)
    study_semester: Mapped[int] = mapped_column(Integer)
    sub_class: Mapped[str] = mapped_column(String(10), default="")
    label: Mapped[str] = mapped_column(String(120))
    # None until known: the snapshot gives counts per programme/year/semester, not per sub-class.
    student_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Slots (0-59) this class row can't be taught, e.g. teaching practice.
    unavailable: Mapped[list[int]] = mapped_column(JSON, default=list)


class UnitOffering(Base):
    """A unit taught this term, owned by one department, with its weekly pattern."""

    __tablename__ = "unit_offerings"
    __table_args__ = (UniqueConstraint("term_id", "smarttt_unit_id", name="uq_offering_unit"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    smarttt_unit_id: Mapped[int] = mapped_column(Integer)
    unit_code: Mapped[str] = mapped_column(String(64))
    unit_name: Mapped[str] = mapped_column(String(255))
    owning_department_id: Mapped[int] = mapped_column(Integer)
    # Set by the Director (prefilled from the last published timetable when there is one).
    weekly_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    room_type: Mapped[str] = mapped_column(String(30), default="lecture_hall")
    source: Mapped[str] = mapped_column(String(30))  # curriculum | published | manual

    class_rows: Mapped[list[OfferingClassRow]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    groups: Mapped[list[Group]] = relationship(cascade="all, delete-orphan", lazy="selectin", order_by="Group.label")

    def session_lengths(self) -> list[int]:
        """The weekly sessions: e.g. 3 h in 2 h sessions -> [2, 1]."""
        if not self.weekly_hours or not self.session_length:
            return []
        full, rest = divmod(self.weekly_hours, self.session_length)
        return [self.session_length] * full + ([rest] if rest else [])


class OfferingClassRow(Base):
    """Which class rows take the offering."""

    __tablename__ = "offering_class_rows"

    offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("unit_offerings.id", ondelete="CASCADE"), primary_key=True
    )
    class_row_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("class_rows.id", ondelete="CASCADE"), primary_key=True)


class Group(Base):
    """One class of an offering ("GR A"; "" when the unit isn't split). The Director decides the split."""

    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("offering_id", "label", name="uq_group_label"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    offering_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unit_offerings.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(50), default="")
    members: Mapped[list[GroupClassRow]] = relationship(cascade="all, delete-orphan", lazy="selectin")

    @property
    def student_count(self) -> int:
        return sum(m.students for m in self.members)


class GroupClassRow(Base):
    __tablename__ = "group_class_rows"

    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    class_row_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("class_rows.id", ondelete="CASCADE"), primary_key=True)
    students: Mapped[int] = mapped_column(Integer)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_term_created", "term_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("snapshots.id", ondelete="RESTRICT"))
    mode: Mapped[RunMode] = mapped_column(_enum(RunMode, "run_mode"))
    base_draft_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drafts.id", ondelete="SET NULL"), nullable=True)
    weights: Mapped[dict[str, int]] = mapped_column(JSON)
    time_limit_s: Mapped[int] = mapped_column(Integer)
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"), default=RunStatus.QUEUED)
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    soft_scores: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    solve_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    failure: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_draft_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    parent_draft_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[DraftStatus] = mapped_column(_enum(DraftStatus, "draft_status"), default=DraftStatus.DRAFT)
    soft_scores: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    sessions: Mapped[list[DraftSession]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="DraftSession.key"
    )


class DraftSession(Base):
    """One timetabled meeting of a group in a draft. `key` stays the same across drafts and versions."""

    __tablename__ = "draft_sessions"
    __table_args__ = (UniqueConstraint("draft_id", "key", name="uq_draft_session_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(120))
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer)
    smarttt_room_id: Mapped[str] = mapped_column(String(64))
    start_slot: Mapped[int] = mapped_column(Integer)  # 0-59, see app.solver.model
    length: Mapped[int] = mapped_column(Integer)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)


class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (UniqueConstraint("term_id", "version", name="uq_publication_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    draft_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drafts.id", ondelete="RESTRICT"))
    published_by: Mapped[str] = mapped_column(String(255))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    smarttt_response: Mapped[dict[str, Any]] = mapped_column(JSON)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_entity", "entity", "entity_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_account_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(128))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    identity: Mapped[dict[str, Any]] = mapped_column(JSON)
    identity_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str] = mapped_column(Text, default="")


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempt_key_at", "key", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(255))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
