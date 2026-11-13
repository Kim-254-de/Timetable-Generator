"""
The exam timetable problem, independent of the database.

Exams run on real dates: the exam period's days, each with the same sessions
(by default 08:30-10:30, 11:30-13:30, 14:30-16:30). A slot is one session of
one day: slot = day index x sessions per day + session.

Hard rules:
  H-E1 no class row sits two papers in one slot;
  H-E2 at most two papers per class row per day;
  H-E3 a slot's students fit the exam seats of all rooms, and when generating
       no more than session_fill percent of them, so that papers needn't be cut
       up to fit the last gaps. A session may pass that only for a paper bigger
       than the limit or for pinned papers; if no timetable holds to it, the run
       uses all the seats (session_limit());
  H-E4 papers only in the period's slots, pinned papers stay;
  H-E6 every class row (or part of one) sits in one room, rooms within their
       exam seats, a paper's ODEL students apart from its other students;
  H-E7 a main invigilator named before generating is in one room per slot: their
       papers go in different sessions, except postgraduate ones, which share a room;
  H-E8 postgraduate papers only in the first or last session
       of a day;
  H-E10 postgraduate papers only in the first week of the period.
Soft rules (weighted): S-E1 back-to-back sessions for a class row, S-E2 two
papers on one day for a class row, S-E3 big papers late in the period.

Papers nobody is known to sit (no class rows, or only a class the department's
page guessed so it could take a number: nobody synced the unit yet) are still
kept apart, by a guess: units of one subject and year ("BPPA 110",
"BPPA 121": BPPA, year 1) are usually sat by the same class. S-E4 keeps such a
guessed class to one paper a session and two a day, and S-E5 spreads these
papers evenly over the period instead of stacking them in one session. Both
are soft (heavily weighted): a guess must never make a timetable impossible.

Postgraduate papers (a code numbered 7xx to 9xx) sit only in the first or last
session of a day, on any exam day (H-E8). Common units (sat by more than one
programme, or with nobody known to sit them, codes from more than one programme:
"BITE 131/COSC 130") prefer those sessions, and take a middle one when the
timetable needs it (S-E9). Some shared units have no programmes on record, so a
paper of more than COMMON_STUDENTS students also counts as common.
Postgraduate papers also sit only in the first week: from the first exam day to
the Friday of that week, so Tuesday to Friday when exams start on a Tuesday (a
Saturday or Sunday start runs to the next Friday) (H-E10).
All of a session's
postgraduate papers share one room when they fit, undergraduates kept out of it
while there is another room (S-E8). So do a session's certificate papers (codes
numbered 00..., "COSC 00101") and its diploma papers (0..., "DIBM 0112"), each
level in its own room; that is all their level changes.
Common papers spread over the days (S-E7).
Weight category_rules 0 turns H-E8 and H-E10 off, and postgraduate_first_week 0
turns H-E10 off alone, as for drafts made before them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

_CODE = re.compile(r"^\s*([A-Za-z]{2,6})\s*-?\s*0*([1-9])\d*")
_LETTERS = re.compile(r"^\s*([A-Za-z]{2,6})")
_POSTGRADUATE = re.compile(r"^\s*[A-Za-z]{2,6}\s*-?\s*[7-9]\d{2,3}[A-Za-z]?\s*$")
_LEADING_ZEROS = re.compile(r"^\s*[A-Za-z]{2,6}\s*-?\s*(0+)[1-9]\d*[A-Za-z]?\s*$")
POSTGRADUATE, COMMON, REGULAR = "postgraduate", "common", "regular"
CATEGORIES = (POSTGRADUATE, COMMON, REGULAR)
COMMON_STUDENTS = 3000  # more students than this and a paper counts as common
CERTIFICATE, DIPLOMA = "certificate", "diploma"  # levels that share a venue; not categories
FRIDAY = 4  # date.weekday()


def paper_kind(codes: list[str] | tuple[str, ...], override: str | None = None) -> str:
    """
    What a paper is from its codes, or the Director's choice: "postgraduate", "regular",
    "common". "" leaves it to the class rows and numbers. A choice of a category that no
    longer exists ("health", set before it was revoked) counts for nothing.
    """
    if override in CATEGORIES:
        return override
    return POSTGRADUATE if any(_POSTGRADUATE.match(c) for c in codes) else ""


def _level(code: str) -> str | None:
    m = _LEADING_ZEROS.match(code)
    if not m:
        return None
    return CERTIFICATE if len(m.group(1)) >= 2 else DIPLOMA


def venue_group(kind: str, codes: tuple[str, ...]) -> str | None:
    """Whose papers share one room in a session (S-E8). Certificate or diploma only when all its codes say so."""
    if kind == POSTGRADUATE:
        return POSTGRADUATE
    levels = {_level(c) for c in codes}
    return levels.pop() if len(levels) == 1 else None


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
    guessed: bool = False  # the class is a guess from the code: it takes seats, but no hard rule holds it


@dataclass(frozen=True)
class Paper:
    id: str
    label: str  # "BITE 131/COSC 130"
    rows: tuple[Sitting, ...]
    pinned: int | None = None  # slot, when the Director pinned it
    previous: int | None = None  # where a re-solve's base draft had it (a hint)
    invigilator: str | None = None  # the main invigilator's staff number, when named before generating
    codes: tuple[str, ...] = ()  # its unit codes, to guess who sits it when no class row is known
    kind: str = ""  # paper_kind(): "" is decided by its class rows (ExamProblem.category)
    fixed_seats: tuple[Seat, ...] = ()  # the venues the Director chose on the draft: kept when the session is re-seated

    @property
    def unknown_students(self) -> bool:
        return not self.row_ids

    @property
    def no_numbers(self) -> bool:
        """No student number yet (S-E5): nothing but this keeps such papers out of one session."""
        return self.students == 0

    @property
    def students(self) -> int:
        return sum(r.students for r in self.rows)

    @property
    def row_ids(self) -> frozenset[str]:
        """The classes known to sit it: the ones the hard rules hold apart."""
        return frozenset(r.row_id for r in self.rows if not r.guessed)


@dataclass(frozen=True)
class ExamWeights:
    back_to_back: int = 50  # S-E1 per class row with papers in consecutive sessions of a day
    same_day: int = 10  # S-E2 per class row with two papers on one day
    big_late: int = 1  # S-E3 per 100 students per day into the period
    guessed_clash: int = 1000  # S-E4 per extra paper of a guessed class in one session
    guessed_day: int = 200  # S-E4 per paper of a guessed class over two on a day
    spread: int = 20  # S-E5 per paper with no students known over an even share of a session
    common_spread: int = 30  # S-E7 per common paper over an even share of a day
    common_midday: int = 1000  # S-E9 per common paper outside the first and last sessions
    category_rules: int = 1  # 0 turns H-E8 and H-E10 off
    postgraduate_first_week: int = 1  # 0 turns H-E10 off
    session_fill: int = 85  # H-E3 when generating: the percent of the exam seats a session may fill; 100 is all

    @classmethod
    def from_dict(cls, data: dict[str, int] | None) -> ExamWeights:
        if not data:
            return cls()
        data = {k: v for k, v in data.items() if k not in ("common_day", "common_by_numbers")}  # retired rules
        known = set(cls.__dataclass_fields__)
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown weights: {', '.join(sorted(unknown))}")
        if any(not isinstance(v, int) or v < 0 for v in data.values()):
            raise ValueError("Weights must be whole numbers from 0.")
        if not 1 <= data.get("session_fill", 100) <= 100:
            raise ValueError("session_fill must be a percent from 1 to 100.")
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
    row_programmes: dict[str, str] = field(default_factory=dict)  # class row -> programme code, for common units
    postgraduate_room: str | None = None  # the room id postgraduate papers sit in first ("TC 1"); see rooms.py

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

    def session_limit(self) -> int:
        """The students a generated session may hold: at least the biggest paper, at most the seats."""
        seats = self.total_seats
        wanted = seats * self.weights.session_fill // 100
        return min(seats, max(wanted, max((p.students for p in self.papers), default=0)))

    def is_common(self, paper: Paper) -> bool:
        """Sat by more than one programme; with no class rows, codes from more than one programme."""
        if paper.row_ids:
            return len({self.row_programmes[r] for r in paper.row_ids if r in self.row_programmes}) > 1
        return len({m.group(1).upper() for m in map(_LETTERS.match, paper.codes) if m}) > 1

    def category(self, paper: Paper) -> str:
        if paper.kind:
            return paper.kind
        return COMMON if self.is_common(paper) or paper.students > COMMON_STUDENTS else REGULAR

    @property
    def rules_on(self) -> bool:
        return bool(self.weights.category_rules)

    def edges_only(self, paper: Paper) -> bool:
        """It may sit only in the first or last session of a day (H-E8)."""
        return self.rules_on and self.category(paper) == POSTGRADUATE

    def is_edge(self, slot: int) -> bool:
        return self.session_of(slot) in (0, self.sessions - 1)

    def edge_slots(self) -> list[int]:
        return [t for t in range(self.slots) if self.is_edge(t)]

    def first_week_only(self, paper: Paper) -> bool:
        """A postgraduate paper may sit only in the first week (H-E10)."""
        if not self.rules_on or not self.weights.postgraduate_first_week:
            return False
        return self.category(paper) == POSTGRADUATE

    def in_first_week(self, slot: int) -> bool:
        """From the first exam day to the Friday of that week; a weekend start runs to the next Friday."""
        start = self.days[0]
        return (self.days[self.day_of(slot)] - start).days <= (FRIDAY - start.weekday()) % 7

    def allowed_slots(self, paper: Paper) -> list[int]:
        """The slots a paper's category lets it sit in (H-E8 and H-E10)."""
        slots = self.edge_slots() if self.edges_only(paper) else list(range(self.slots))
        return [t for t in slots if self.in_first_week(t)] if self.first_week_only(paper) else slots

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
