"""
The timetabling problem as the solver sees it: plain data, no database.

The teaching week is Monday-Friday, 07:00-19:00 (H7): 5 days x 12 one-hour
slots = 60 slots. Slot t is day t // 12, hour 7 + t % 12.

A *session* is one weekly meeting of a group (e.g. COSC 103 GR A, 2 hours).
A group of a unit offering serves one or more class rows; an unsplit unit has
one group. When one large class row is split across groups of a unit (GR A,
GR B ...), each student attends only their own group, so the groups may meet
together in different rooms or at different times (e.g. rotating labs); the
row's other classes keep clear of all of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DAYS = ("MON", "TUE", "WED", "THU", "FRI")
FIRST_HOUR = 7
HOURS_PER_DAY = 12
SLOTS = len(DAYS) * HOURS_PER_DAY


def slot(day: int, hour: int) -> int:
    """Slot index for day 0-4 and clock hour 7-18."""
    return day * HOURS_PER_DAY + (hour - FIRST_HOUR)


def slot_day(t: int) -> int:
    return t // HOURS_PER_DAY


def slot_hour(t: int) -> int:
    return FIRST_HOUR + t % HOURS_PER_DAY


def covered(start: int, length: int) -> range:
    return range(start, start + length)


def valid_start(start: int, length: int) -> bool:
    """A session starts and ends on the same day, inside teaching hours (H6, H7)."""
    if start < 0 or length < 1 or start + length > SLOTS:
        return False
    return slot_day(start) == slot_day(start + length - 1)


@dataclass(frozen=True)
class Room:
    id: str
    code: str
    building: str
    capacity: int
    room_type: str
    unavailable: frozenset[int] = frozenset()


@dataclass(frozen=True)
class ClassRow:
    id: str
    label: str
    unavailable: frozenset[int] = frozenset()


@dataclass(frozen=True)
class Placement:
    start: int
    room_id: str


@dataclass(frozen=True)
class Session:
    key: str
    offering_id: str
    group_id: str
    index: int  # k-th weekly session of the group (0-based)
    label: str  # "COSC 103 GR A #1", for messages
    department_id: int
    class_row_ids: tuple[str, ...]
    students: int
    length: int
    room_type: str
    pinned: Placement | None = None  # H10: keeps slot and room
    previous: Placement | None = None  # repair re-solves: where it was (S8), and a hint
    # The group's lecturer (staff number), so H13 keeps them to one class at a time;
    # a session without one counts against its department's lecturers instead (H9).
    lecturer_id: str | None = None
    lecturer_name: str = ""  # for messages


@dataclass(frozen=True)
class Weights:
    """Soft-constraint weights (penalty per unit). 0 turns a preference off."""

    gaps: int = 100  # S1 one-hour gap in a class row's day
    same_day: int = 80  # S2 two sessions of one group on the same day
    long_day: int = 30  # S3 per hour over 5 teaching hours in a class row's day
    edge_hours: int = 20  # S4 per session-hour at 07:00 or from 17:00
    department_peak: int = 5  # S5 per unit of a department's busiest hour
    building_changes: int = 5  # S6 per extra building a class row uses in a day
    room_fit: int = 1  # S7 per 10 empty seats
    keep_previous: int = 1000  # S8 per session moved from where it was (repair only)

    @classmethod
    def from_dict(cls, data: dict[str, int] | None) -> Weights:
        if not data:
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown weights: {', '.join(sorted(unknown))}")
        if any(not isinstance(v, int) or v < 0 for v in data.values()):
            raise ValueError("Weights must be whole numbers from 0.")
        return cls(**data)

    def as_dict(self) -> dict[str, int]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


@dataclass
class Problem:
    rooms: list[Room]
    class_rows: list[ClassRow]
    sessions: list[Session]
    # H9: lecturers (full-time + part-time) per department = classes it can run at once.
    department_capacity: dict[int, int]
    weights: Weights = field(default_factory=Weights)
    # H9 is skipped for departments not listed; True makes a missing one an error instead.
    require_department_capacity: bool = True

    def rooms_by_id(self) -> dict[str, Room]:
        return {r.id: r for r in self.rooms}

    def rows_by_id(self) -> dict[str, ClassRow]:
        return {r.id: r for r in self.class_rows}


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    session_keys: tuple[str, ...] = ()


@dataclass
class Solution:
    placements: dict[str, Placement]
    status: str  # OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN | MODEL_INVALID
    objective: float | None = None
    soft_scores: dict[str, float] = field(default_factory=dict)
    solve_seconds: float = 0.0
    failure: dict[str, object] | None = None
