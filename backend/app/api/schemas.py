from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

HHMM = r"^([01]\d|2[0-3]):00$"
Day = Literal["MON", "TUE", "WED", "THU", "FRI"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginBody(_Strict):
    identifier: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=1024)]


Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
RoomType = Literal["lecture_hall", "lab", "seminar"]
Slots = Annotated[list[Annotated[int, Field(ge=0, le=59)]], Field(max_length=60)]
AcademicYear = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{4}/\d{4}$")]


class OpenTermBody(_Strict):
    """Either open a SMARTTT term (`smarttt_term_id`) or create one here (`academic_year` + `semester`)."""

    smarttt_term_id: Annotated[str, StringConstraints(min_length=1, max_length=64)] | None = None
    academic_year: AcademicYear | None = None
    semester: Annotated[int, Field(ge=1, le=3)] | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    start_date: date | None = None
    end_date: date | None = None
    version_label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    use_from: date | None = None
    prepared_by: Text | None = None
    prepared_by_title: Text | None = None
    default_session_length: Annotated[int, Field(ge=1, le=6)] | None = None
    copy_from_term_id: uuid.UUID | None = None


class TermPatch(_Strict):
    academic_year: AcademicYear | None = None
    semester: Annotated[int, Field(ge=1, le=3)] | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    start_date: date | None = None
    end_date: date | None = None
    version_label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    use_from: date | None = None
    prepared_by: Text | None = None
    prepared_by_title: Text | None = None
    default_session_length: Annotated[int, Field(ge=1, le=6)] | None = None


class RoomBody(_Strict):
    code: Code
    building: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    capacity: Annotated[int, Field(ge=1, le=5000)]
    room_type: RoomType = "lecture_hall"
    active: bool = True
    unavailable: Slots = []


class RoomPatch(_Strict):
    code: Code | None = None
    building: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    capacity: Annotated[int, Field(ge=1, le=5000)] | None = None
    room_type: RoomType | None = None
    active: bool | None = None
    unavailable: Slots | None = None


# A department typed by name or code; a name not yet in the Departments list is added to it.
DepartmentText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class DepartmentBody(_Strict):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    school: Text = ""
    lecturer_count: Annotated[int, Field(ge=1, le=2000)] | None = None


class DepartmentPatch(_Strict):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)] | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] | None = None
    school: Text | None = None
    lecturer_count: Annotated[int, Field(ge=0, le=2000)] | None = None  # 0 clears the count


class ClassRowBody(_Strict):
    program_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    study_year: Annotated[int, Field(ge=1, le=7)]
    study_semester: Annotated[int, Field(ge=1, le=3)]
    sub_class: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10)] = ""
    department_id: int | None = None
    department: DepartmentText | None = None
    student_count: Annotated[int, Field(ge=0, le=5000)] | None = None
    unavailable: Slots = []


class ClassRowPatch(_Strict):
    program_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] | None = None
    study_year: Annotated[int, Field(ge=1, le=7)] | None = None
    study_semester: Annotated[int, Field(ge=1, le=3)] | None = None
    sub_class: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10)] | None = None
    department_id: int | None = None
    department: DepartmentText | None = None
    student_count: Annotated[int, Field(ge=0, le=5000)] | None = None
    unavailable: Slots | None = None


class OfferingBody(_Strict):
    unit_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=64)]
    unit_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    department_id: int | None = None  # this or `department` is required
    department: DepartmentText | None = None
    weekly_hours: Annotated[int, Field(ge=1, le=20)] | None = None
    session_length: Annotated[int, Field(ge=1, le=6)] | None = None
    room_type: RoomType = "lecture_hall"
    class_row_ids: Annotated[list[uuid.UUID], Field(max_length=200)] = []


class OfferingPatch(_Strict):
    unit_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=64)] | None = None
    unit_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] | None = None
    department_id: int | None = None
    department: DepartmentText | None = None
    weekly_hours: Annotated[int, Field(ge=1, le=20)] | None = None
    session_length: Annotated[int, Field(ge=1, le=6)] | None = None
    room_type: RoomType | None = None
    class_row_ids: Annotated[list[uuid.UUID], Field(max_length=200)] | None = None


class BulkBody(_Strict):
    """Rows pasted from Excel or read from a CSV, already split into fields by the browser."""

    rows: Annotated[list[dict[str, Any]], Field(min_length=1, max_length=3000)]


class CopyTermBody(_Strict):
    source_term_id: uuid.UUID


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
    # Keep every class of the published timetable where it is (a late department was imported).
    keep_published: bool = False


class MoveBody(_Strict):
    day: Day | None = None
    start_time: Annotated[str, StringConstraints(pattern=HHMM)] | None = None
    room_id: Annotated[str, StringConstraints(min_length=1, max_length=64)] | None = None
    pinned: bool | None = None


class PublishBody(_Strict):
    replace_unpublished: bool = False
