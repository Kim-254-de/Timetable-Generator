"""
The exam timetable problem, independent of the database.

Exams run on real dates: the exam period's days, each with the same sessions
(by default 08:30-10:30, 11:30-13:30, 14:30-16:30). A slot is one session of
one day: slot = day index x sessions per day + session.

Hard rules:
  H-E1 no class row sits two papers in one slot;
  H-E2 at most two papers per class row per day;
  H-E3 a slot's students fit the exam seats of all rooms;
  H-E4 papers only in the period's slots, pinned papers stay;
  H-E6 every class row (or part of one) sits in one room, rooms within their
       exam seats, a paper's ODEL students apart from its other students;
  H-E7 a main invigilator named before generating is in one paper per slot.
Soft rules (weighted): S-E1 back-to-back sessions for a class row, S-E2 two
papers on one day for a class row, S-E3 big papers late in the period.

Papers nobody is known to sit (no class rows: nobody synced the unit yet) are
still kept apart, by a guess: units of one subject and year ("BPPA 110",
"BPPA 121": BPPA, year 1) are usually sat by the same class. S-E4 keeps such a
guessed class to one paper a session and two a day, and S-E5 spreads these
papers evenly over the period instead of stacking them in one session. Both
are soft (heavily weighted): a guess must never make a timetable impossible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

_CODE = re.compile(r"^\s*([A-Za-z]{2,6})\s*-?\s*0*([1-9])\d*")


def guessed_class(code: str) -> str | None:
    """'BPPA 110' -> 'BPPA year 1'; 'COSC 0172' -> 'COSC year 1'; None when the code doesn't say."""
    m = _CODE.match(code)
    return f"{m.group(1).upper()} year {m.group(2)}" if m else None


@dataclass(frozen=True)
class ExamRoom:
    id: str
    code: str
    block: str  # the building block a big paper is kept within
    seats: int  # exam seats


@dataclass(frozen=True)
class Sitting:
    """A class row sitting a paper."""

    row_id: str
    students: int
    odel: bool = False


@dataclass(frozen=True)
class Paper:
    id: str
    label: str  # "BITE 131/COSC 130"
    rows: tuple[Sitting, ...]
    pinned: int | None = None  # slot, when the Director pinned it
    previous: int | None = None  # where a re-solve's base draft had it (a hint)
    invigilator: str | None = None  # the main invigilator's staff number, when named before generating
    codes: tuple[str, ...] = ()  # its unit codes, to guess who sits it when no class row is known

    @property
    def unknown_students(self) -> bool:
        return not self.rows

    @property
    def students(self) -> int:
        return sum(r.students for r in self.rows)

    @property
    def row_ids(self) -> frozenset[str]:
        return frozenset(r.row_id for r in self.rows)


@dataclass(frozen=True)
class ExamWeights:
    back_to_back: int = 50  # S-E1 per class row with papers in consecutive sessions of a day
    same_day: int = 10  # S-E2 per class row with two papers on one day
    big_late: int = 1  # S-E3 per 100 students per day into the period
    guessed_clash: int = 1000  # S-E4 per extra paper of a guessed class in one session
    guessed_day: int = 200  # S-E4 per paper of a guessed class over two on a day
    spread: int = 20  # S-E5 per paper with no students known over an even share of a session

    @classmethod
    def from_dict(cls, data: dict[str, int] | None) -> ExamWeights:
        if not data:
            return cls()
        known = set(cls.__dataclass_fields__)
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown weights: {', '.join(sorted(unknown))}")
        if any(not isinstance(v, int) or v < 0 for v in data.values()):
            raise ValueError("Weights must be whole numbers from 0.")
        return cls(**data)

    def as_dict(self) -> dict[str, int]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


@dataclass
class ExamProblem:
    papers: list[Paper]
    days: list[date]
    sessions: int
    rooms: list[ExamRoom]
    weights: ExamWeights = field(default_factory=ExamWeights)
    row_labels: dict[str, str] = field(default_factory=dict)  # for messages

    def row_label(self, row_id: str) -> str:
        return self.row_labels.get(row_id, row_id)

    @property
    def slots(self) -> int:
        return len(self.days) * self.sessions

    def day_of(self, slot: int) -> int:
        return slot // self.sessions

    def session_of(self, slot: int) -> int:
        return slot % self.sessions

    @property
    def total_seats(self) -> int:
        return sum(r.seats for r in self.rooms)

    def invigilators(self) -> dict[str, list[Paper]]:
        """Each main invigilator's papers, for those named before generating."""
        out: dict[str, list[Paper]] = {}
        for p in self.papers:
            if p.invigilator:
                out.setdefault(p.invigilator, []).append(p)
        return out

    def guessed_classes(self) -> dict[str, list[Paper]]:
        """Papers nobody is known to sit, by the class their codes suggest (S-E4)."""
        out: dict[str, list[Paper]] = {}
        for p in self.papers:
            if not p.unknown_students:
                continue
            for group in sorted({g for g in map(guessed_class, p.codes) if g}):
                out.setdefault(group, []).append(p)
        return out

    def rows(self) -> dict[str, list[Paper]]:
        """Each class row's papers."""
        out: dict[str, list[Paper]] = {}
        for p in self.papers:
            for r in p.row_ids:
                out.setdefault(r, []).append(p)
        return out


@dataclass(frozen=True)
class Seat:
    """Where a class row (or part `part` of `parts` of it) sits a paper."""

    paper_id: str
    row_id: str
    room_id: str
    students: int
    part: int = 1
    parts: int = 1


@dataclass(frozen=True)
class ExamViolation:
    rule: str
    message: str
    paper_ids: tuple[str, ...] = ()


@dataclass
class ExamSolution:
    slots: dict[str, int]  # paper id -> slot
    seats: list[Seat]
    status: str  # OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN
    soft_scores: dict[str, float] = field(default_factory=dict)
    solve_seconds: float = 0.0
    failure: dict[str, object] | None = None
