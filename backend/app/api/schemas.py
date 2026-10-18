from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

HHMM = r"^([01]\d|2[0-3]):00$"
Day = Literal["MON", "TUE", "WED", "THU", "FRI"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginBody(_Strict):
    identifier: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class OpenTermBody(_Strict):
    smarttt_term_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class ClassRowPatch(_Strict):
    student_count: Annotated[int, Field(ge=0, le=5000)] | None = None
    unavailable: Annotated[list[Annotated[int, Field(ge=0, le=59)]], Field(max_length=60)] | None = None


class OfferingPatch(_Strict):
    weekly_hours: Annotated[int, Field(ge=1, le=20)] | None = None
    session_length: Annotated[int, Field(ge=1, le=6)] | None = None
    room_type: Literal["lecture_hall", "lab", "seminar"] | None = None


class GroupMember(_Strict):
    class_row_id: uuid.UUID
    students: Annotated[int, Field(ge=1, le=5000)]


class GroupBody(_Strict):
    label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
    members: Annotated[list[GroupMember], Field(min_length=1, max_length=100)]


class ProposeBody(_Strict):
    replace: bool = False


class RunBody(_Strict):
    term_id: uuid.UUID
    mode: Literal["full", "repair"] = "full"
    weights: dict[str, Annotated[int, Field(ge=0, le=100_000)]] | None = None
    time_limit_s: Annotated[int, Field(ge=10, le=3600)] | None = None
    base_draft_id: uuid.UUID | None = None


class ResolveBody(_Strict):
    weights: dict[str, Annotated[int, Field(ge=0, le=100_000)]] | None = None
    time_limit_s: Annotated[int, Field(ge=10, le=3600)] | None = None


class MoveBody(_Strict):
    day: Day | None = None
    start_time: Annotated[str, StringConstraints(pattern=HHMM)] | None = None
    room_id: Annotated[str, StringConstraints(min_length=1, max_length=64)] | None = None
    pinned: bool | None = None


class PublishBody(_Strict):
    replace_unpublished: bool = False
