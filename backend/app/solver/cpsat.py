"""
Two-phase CP-SAT solver.

Solving time and room together is ~900 sessions x 60 hours x ~90 rooms
booleans, too many. So:

Phase 1 - time. Each session picks one start among its feasible starts
(b[s, p], exactly one). Whether it covers slot t is the linear sum of the
starts that cover t. Hard rules:
  H2  per class row and slot, at most one class (a row split across
      groups of one unit counts once, whichever of its groups meet then);
  H1/H3/H4 per room type, size threshold and slot, the sessions needing a
      room at least that big fit in the rooms at least that big that are
      free then (a nested Hall condition, so phase 2 can seat them);
  H9  per department and slot, its classes with no lecturer named <= its lecturers;
  H13 per lecturer and slot, at most one class;
  H6/H7/H8/H10 by the start domains.
Soft rules S1-S5 and S8 are weighted penalties.

Phase 2 - rooms. With times fixed, each session picks one suitable room
that is free; no two overlapping sessions share a room. S6, S7 and S8 are
the objective. Solves in seconds.

When phase 1 is infeasible, it is solved again with one assumption literal
per constraint family (each class row, each room size band, each
department, each lecturer) to name the rules that cannot all hold.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model

from app.solver import precheck
from app.solver.model import (
    DAYS,
    HOURS_PER_DAY,
    SLOTS,
    Placement,
    Problem,
    Session,
    Solution,
    covered,
    slot_day,
    slot_hour,
)
from app.solver.scoring import score, weighted
from app.solver.validate import check

logger = logging.getLogger(__name__)

Progress = Callable[[dict[str, object]], None]
# A CP-SAT linear expression. OR-Tools' stubs can't type sums that mix
# variables, expressions and ints, so expressions are left untyped here.
Expr = Any
STATUS = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}
ROOM_CANDIDATES = 12


@dataclass
class TimeUnit:
    """One session's choice of start time."""

    id: int
    sessions: list[Session]
    length: int
    starts: list[int]
    row_ids: set[str] = field(default_factory=set)

    @property
    def label(self) -> str:
        return self.sessions[0].label


def build_units(problem: Problem) -> list[TimeUnit]:
    return [
        TimeUnit(
            id=i,
            sessions=[s],
            length=s.length,
            starts=precheck.feasible_starts(s, problem),
            row_ids=set(s.class_row_ids),
        )
        for i, s in enumerate(problem.sessions)
    ]


class _Progress(cp_model.CpSolverSolutionCallback):
    def __init__(self, on_progress: Progress | None, phase: str):
        super().__init__()
        self._on_progress = on_progress
        self._phase = phase
        self._started = time.monotonic()
        self.solutions = 0

    def on_solution_callback(self) -> None:
        self.solutions += 1
        if self._on_progress is not None:
            self._on_progress(
                {
                    "phase": self._phase,
                    "objective": self.objective_value,
                    "best_bound": self.best_objective_bound,
                    "solutions": self.solutions,
                    "seconds": round(time.monotonic() - self._started, 1),
                }
            )


# ---------------------------------------------------------------------------
# Phase 1: time
# ---------------------------------------------------------------------------


@dataclass
class _Phase1:
    model: cp_model.CpModel
    units: list[TimeUnit]
    b: dict[int, dict[int, cp_model.IntVar]]
    families: dict[str, cp_model.IntVar]
    # Per class row and slot: the terms whose sum is 1 when the row is in class then.
    row_occupancy: dict[str, list[list[Expr]]] = field(default_factory=dict)


def _cover(m: _Phase1, unit: TimeUnit, t: int) -> list[cp_model.IntVar]:
    return [var for p, var in m.b[unit.id].items() if p <= t < p + unit.length]


def _room_thresholds(problem: Problem, room_type: str, sessions: list[Session]) -> list[int]:
    """
    Size bands worth checking: supply only changes at room capacities, so
    demand(>= c) <= supply(>= c) for all c holds when it holds at 1 and just
    above every capacity.
    """
    biggest = max(s.students for s in sessions)
    capacities = sorted({r.capacity for r in problem.rooms if r.room_type == room_type})
    bands = {1} | {c + 1 for c in capacities if c + 1 <= biggest}
    return sorted(bands)


def _build_phase1(problem: Problem, units: list[TimeUnit], with_families: bool) -> _Phase1:
    model = cp_model.CpModel()
    m = _Phase1(model=model, units=units, b={}, families={})

    for u in units:
        m.b[u.id] = {p: model.new_bool_var(f"b{u.id}_{p}") for p in u.starts}
        model.add_exactly_one(m.b[u.id].values())
        previous = u.sessions[0].previous
        if previous is not None and previous.start in m.b[u.id]:
            model.add_hint(m.b[u.id][previous.start], 1)

    def family(name: str) -> list[cp_model.IntVar]:
        if not with_families:
            return []
        lit = m.families.get(name)
        if lit is None:
            lit = m.families[name] = model.new_bool_var(name)
        return [lit]

    def limit(terms: Sequence[Expr], bound: int, name: str) -> None:
        if not terms:
            return
        ct = model.add(sum(terms) <= bound)
        lits = family(name)
        if lits:
            ct.only_enforce_if(lits)

    # H2: one class at a time per class row. When a row is split across
    # several groups of one unit, each student attends only their group, so
    # the sibling groups may meet together or at different times; the row's
    # other classes keep clear of all of them, and each group's own sessions
    # never overlap.
    by_row: dict[str, list[TimeUnit]] = defaultdict(list)
    for u in units:
        for row_id in u.row_ids:
            by_row[row_id].append(u)
    rows = problem.rows_by_id()
    for row_id, row_units in by_row.items():
        label = rows[row_id].label if row_id in rows else row_id
        by_offering: dict[str, list[TimeUnit]] = defaultdict(list)
        for u in row_units:
            by_offering[u.sessions[0].offering_id].append(u)
        occupancy: list[list[Expr]] = [[] for _ in range(SLOTS)]
        for offering_units in by_offering.values():
            groups = {u.sessions[0].group_id for u in offering_units}
            for t in range(SLOTS):
                covering = [v for u in offering_units for v in _cover(m, u, t)]
                if not covering:
                    continue
                if len(groups) == 1:
                    occupancy[t].extend(covering)
                    continue
                for group in groups:
                    own = [v for u in offering_units if u.sessions[0].group_id == group for v in _cover(m, u, t)]
                    if len(own) > 1:
                        limit(own, 1, f"H2|{label}")
                busy = model.new_bool_var("")
                for v in covering:
                    model.add_implication(v, busy)
                model.add(busy <= sum(covering))
                occupancy[t].append(busy)
        m.row_occupancy[row_id] = occupancy
        for t in range(SLOTS):
            if len(occupancy[t]) > 1:
                limit(occupancy[t], 1, f"H2|{label}")

    # H1/H3/H4: enough rooms of each type and size band in every hour.
    by_type: dict[str, list[tuple[TimeUnit, Session]]] = defaultdict(list)
    for u in units:
        for s in u.sessions:
            by_type[s.room_type].append((u, s))
    for room_type, members in by_type.items():
        for c in _room_thresholds(problem, room_type, [s for _u, s in members]):
            needing = [(u, s) for u, s in members if s.students >= c]
            if not needing:
                continue
            rooms = [r for r in problem.rooms if r.room_type == room_type and r.capacity >= c]
            for t in range(SLOTS):
                supply = sum(1 for r in rooms if t not in r.unavailable)
                terms = [v for u, _s in needing for v in _cover(m, u, t)]
                if len(terms) > supply:
                    limit(terms, supply, f"H1|{room_type}|{c}")

    # H9: a department runs at most as many classes at once as it has lecturers.
    # Classes whose lecturer is named are kept apart by H13 instead.
    by_dept: dict[int, list[tuple[TimeUnit, Session]]] = defaultdict(list)
    for u in units:
        for s in u.sessions:
            by_dept[s.department_id].append((u, s))
    for dept, members in by_dept.items():
        cap = problem.department_capacity.get(dept)
        unnamed = [(u, s) for u, s in members if not s.lecturer_id]
        if cap is None or not unnamed:
            continue
        for t in range(SLOTS):
            terms = [v for u, _s in unnamed for v in _cover(m, u, t)]
            if len(terms) > cap:
                limit(terms, cap, f"H9|{dept}")

    # H13: a lecturer teaches one class at a time, across every department.
    by_lecturer: dict[str, list[TimeUnit]] = defaultdict(list)
    for u in units:
        for s in u.sessions:
            if s.lecturer_id:
                by_lecturer[s.lecturer_id].append(u)
    for lecturer, lecturer_units in by_lecturer.items():
        if len(lecturer_units) < 2:
            continue
        for t in range(SLOTS):
            terms = [v for u in lecturer_units for v in _cover(m, u, t)]
            if len(terms) > 1:
                limit(terms, 1, f"H13|{lecturer}")

    if not with_families:
        _phase1_objective(problem, m, by_row, by_dept)
    return m


def _phase1_objective(
    problem: Problem, m: _Phase1, by_row: dict[str, list[TimeUnit]], by_dept: dict[int, list[tuple[TimeUnit, Session]]]
) -> None:
    w = problem.weights
    model = m.model
    cost: list[Expr] = []

    for row_id, row_units in by_row.items():
        if sum(u.length for u in row_units) < 2:
            continue
        occupancy = m.row_occupancy[row_id]
        for d in range(len(DAYS)):
            base = d * HOURS_PER_DAY
            day_occ = [sum(occupancy[base + h]) for h in range(HOURS_PER_DAY)]
            if w.gaps:
                for h in range(1, HOURS_PER_DAY - 1):
                    gap = model.new_bool_var("")
                    model.add(gap >= day_occ[h - 1] + day_occ[h + 1] - day_occ[h] - 1)
                    cost.append(w.gaps * gap)
            if w.long_day:
                excess = model.new_int_var(0, HOURS_PER_DAY, "")
                model.add(excess >= sum(day_occ) - 5)
                cost.append(w.long_day * excess)

    if w.same_day:
        by_group: dict[str, list[TimeUnit]] = defaultdict(list)
        for u in m.units:
            by_group[u.sessions[0].group_id].append(u)
        for group_units in by_group.values():
            for i, a in enumerate(group_units):
                for b_unit in group_units[i + 1 :]:
                    for d in range(len(DAYS)):
                        ya = [v for p, v in m.b[a.id].items() if slot_day(p) == d]
                        yb = [v for p, v in m.b[b_unit.id].items() if slot_day(p) == d]
                        if ya and yb:
                            both = model.new_bool_var("")
                            model.add(both >= sum(ya) + sum(yb) - 1)
                            cost.append(w.same_day * both)

    for u in m.units:
        for p, var in m.b[u.id].items():
            edge = sum(1 for t in covered(p, u.length) if slot_hour(t) == 7 or slot_hour(t) >= 17)
            if edge and w.edge_hours:
                cost.append(w.edge_hours * edge * len(u.sessions) * var)
        previous = u.sessions[0].previous
        if previous is not None and w.keep_previous:
            kept = m.b[u.id].get(previous.start)
            moved = len(u.sessions) * w.keep_previous
            cost.append(moved - moved * kept if kept is not None else moved)

    if w.department_peak:
        for members in by_dept.values():
            peak = model.new_int_var(0, len(members), "")
            for t in range(SLOTS):
                terms = [v for u, _s in members for v in _cover(m, u, t)]
                if terms:
                    model.add(peak >= sum(terms))
            cost.append(w.department_peak * peak)

    model.minimize(sum(cost))


def _family_message(name: str, problem: Problem) -> dict[str, str]:
    rule, *rest = name.split("|")
    if rule == "H2":
        return {"rule": "H2", "entity": rest[0], "message": f"{rest[0]}'s classes cannot all fit without clashing."}
    if rule == "H1":
        room_type, size = rest
        return {
            "rule": "H1",
            "entity": f"{room_type} >= {size}",
            "message": f"Not enough {room_type.replace('_', ' ')}s seating {size}+ at the hours needed.",
        }
    if rule == "H9":
        cap = problem.department_capacity.get(int(rest[0]))
        return {
            "rule": "H9",
            "entity": f"department {rest[0]}",
            "message": f"Department {rest[0]} would need more than its {cap} lecturers in some hour.",
        }
    return {
        "rule": "H13",
        "entity": f"lecturer {rest[0]}",
        "message": "An allocated lecturer's classes cannot all keep clear of each other.",
    }


def explain_infeasible(problem: Problem, units: list[TimeUnit], time_limit_s: float) -> list[dict[str, str]]:
    m = _build_phase1(problem, units, with_families=True)
    lits = list(m.families.values())
    m.model.add_assumptions(lits)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 1  # assumption cores need a single worker
    status = solver.solve(m.model)
    if status != cp_model.INFEASIBLE:
        return [
            {
                "rule": "?",
                "entity": "timetable",
                "message": "No timetable was found in the time limit; try a longer run.",
            }
        ]
    names = {v.index: k for k, v in m.families.items()}
    core = [names[i] for i in solver.sufficient_assumptions_for_infeasibility() if i in names]
    return [_family_message(name, problem) for name in sorted(core)]


def solve_times(
    problem: Problem, units: list[TimeUnit], deadline: float, share: float, workers: int, on_progress: Progress | None
) -> tuple[str, dict[int, int], float | None]:
    """Phase 1, given `share` of the time left before `deadline` (time.monotonic()) once the model is built."""
    m = _build_phase1(problem, units, with_families=False)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(5.0, (deadline - time.monotonic()) * share)
    solver.parameters.num_workers = workers
    callback = _Progress(on_progress, "time")
    status = solver.solve(m.model, callback)
    name = STATUS.get(status, "UNKNOWN")
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return name, {}, None
    starts = {u.id: next(p for p, v in m.b[u.id].items() if solver.value(v)) for u in units}
    return name, starts, solver.objective_value


# ---------------------------------------------------------------------------
# Phase 2: rooms
# ---------------------------------------------------------------------------


def greedy_rooms(problem: Problem, starts: dict[str, int]) -> dict[str, str] | None:
    """
    A room for every session, or None: sessions in order of start time each
    take the smallest suitable free room (their previous room, then a
    building their class rows already use that day, breaking ties). Phase 1's
    per-hour room counts make this succeed in practice; it seeds CP-SAT and
    is the fallback when CP-SAT runs out of time.
    """
    sessions = {s.key: s for s in problem.sessions}
    busy: set[tuple[str, int]] = set()
    rooms = problem.rooms_by_id()
    row_buildings: dict[tuple[str, int], set[str]] = defaultdict(set)
    chosen: dict[str, str] = {}
    order = sorted(starts, key=lambda k: (sessions[k].pinned is None, starts[k], -sessions[k].students))
    for key in order:
        s, start = sessions[key], starts[key]
        hours = list(covered(start, s.length))
        options = _candidates(problem, s, start, None)
        free = [r for r in options if not any((r, t) in busy for t in hours)]
        if not free:
            return None
        day = slot_day(start)
        used = set().union(*(row_buildings[(row, day)] for row in s.class_row_ids))
        prev = s.previous.room_id if s.previous is not None and s.previous.start == start else None
        best = min(free, key=lambda r: (r != prev, rooms[r].capacity - s.students, rooms[r].building not in used))
        chosen[key] = best
        busy.update((best, t) for t in hours)
        for row in s.class_row_ids:
            row_buildings[(row, day)].add(rooms[best].building)
    return chosen


def _candidates(problem: Problem, s: Session, start: int, limit: int | None, extra: str | None = None) -> list[str]:
    if s.pinned is not None:
        return [s.pinned.room_id]
    hours = set(covered(start, s.length))
    fitting = [
        r
        for r in problem.rooms
        if r.room_type == s.room_type and r.capacity >= s.students and not hours & r.unavailable
    ]
    fitting.sort(key=lambda r: r.capacity - s.students)
    chosen = fitting if limit is None else fitting[:limit]
    wanted = {extra} if extra else set()
    if s.previous is not None and s.previous.start == start:
        wanted.add(s.previous.room_id)
    chosen += [r for r in fitting if r.id in wanted and r not in chosen]
    return [r.id for r in chosen]


def solve_rooms(
    problem: Problem,
    starts: dict[str, int],
    time_limit_s: float,
    workers: int,
    limit: int | None,
    on_progress: Progress | None,
    seed: dict[str, str] | None = None,
) -> tuple[str, dict[str, str]]:
    w = problem.weights
    rooms = problem.rooms_by_id()
    model = cp_model.CpModel()
    z: dict[str, dict[str, cp_model.IntVar]] = {}
    cost: list[Expr] = []
    per_room_slot: dict[tuple[str, int], list[cp_model.IntVar]] = defaultdict(list)
    sessions = {s.key: s for s in problem.sessions}

    for key, start in starts.items():
        s = sessions[key]
        options = _candidates(problem, s, start, limit, (seed or {}).get(key))
        if not options:
            return "INFEASIBLE", {}
        z[key] = {r: model.new_bool_var("") for r in options}
        model.add_exactly_one(z[key].values())
        for room_id, var in z[key].items():
            for t in covered(start, s.length):
                per_room_slot[(room_id, t)].append(var)
            if w.room_fit:
                cost.append(w.room_fit * ((rooms[room_id].capacity - s.students) // 10) * var)
        if s.previous is not None and s.previous.start == start and w.keep_previous:
            kept = z[key].get(s.previous.room_id)
            cost.append(w.keep_previous - w.keep_previous * kept if kept is not None else w.keep_previous)
        hint = (seed or {}).get(key) or (s.previous.room_id if s.previous is not None else None)
        if hint in z[key]:
            model.add_hint(z[key][hint], 1)

    for vars_ in per_room_slot.values():
        if len(vars_) > 1:
            model.add_at_most_one(vars_)

    if w.building_changes:
        used: dict[tuple[str, int, str], cp_model.IntVar] = {}
        for key, start in starts.items():
            s = sessions[key]
            for row_id in s.class_row_ids:
                for room_id, var in z[key].items():
                    k = (row_id, slot_day(start), rooms[room_id].building)
                    if k not in used:
                        used[k] = model.new_bool_var("")
                        cost.append(w.building_changes * used[k])
                    model.add_implication(var, used[k])

    model.minimize(sum(cost))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = workers
    status = solver.solve(model, _Progress(on_progress, "rooms"))
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return STATUS.get(status, "UNKNOWN"), {}
    return STATUS[status], {key: next(r for r, v in options.items() if solver.value(v)) for key, options in z.items()}


# ---------------------------------------------------------------------------
# Both phases
# ---------------------------------------------------------------------------


def solve(
    problem: Problem, time_limit_s: float = 600, workers: int = 8, on_progress: Progress | None = None
) -> Solution:
    """
    The best timetable found within the time limit, or a failure that says
    why there is none. A returned timetable always passes validate.check.
    """
    started = time.monotonic()
    findings = precheck.run(problem)
    if findings:
        return Solution(
            placements={},
            status="INFEASIBLE",
            solve_seconds=time.monotonic() - started,
            failure={"stage": "precheck", "reasons": [f.__dict__ for f in findings[:50]], "count": len(findings)},
        )

    units = build_units(problem)
    empty = [u.label for u in units if not u.starts]
    if empty:
        return Solution(
            placements={},
            status="INFEASIBLE",
            solve_seconds=time.monotonic() - started,
            failure={
                "stage": "precheck",
                "count": len(empty),
                "reasons": [
                    {"rule": "H8", "entity": label, "message": f"{label}: no free hour left for it."}
                    for label in empty[:50]
                ],
            },
        )

    # The whole run, model building included, keeps to the time limit; rooms get
    # what phase 1 leaves (they usually need well under a minute).
    deadline = started + time_limit_s
    status, unit_starts, _objective = solve_times(problem, units, deadline, 0.85, workers, on_progress)
    if not unit_starts:
        reasons = (
            explain_infeasible(problem, units, min(120.0, time_limit_s))
            if status == "INFEASIBLE"
            else [
                {
                    "rule": "?",
                    "entity": "timetable",
                    "message": "No timetable was found in the time limit; try a longer run or relax pins.",
                }
            ]
        )
        return Solution(
            placements={},
            status=status,
            solve_seconds=time.monotonic() - started,
            failure={"stage": "time", "reasons": reasons, "count": len(reasons)},
        )

    starts = {s.key: unit_starts[u.id] for u in units for s in u.sessions}
    seed = greedy_rooms(problem, starts)
    remaining = max(15.0, deadline - time.monotonic())
    room_status, room_of = solve_rooms(problem, starts, remaining, workers, ROOM_CANDIDATES, on_progress, seed)
    if not room_of and seed is not None:
        room_status, room_of = "FEASIBLE", seed
    if not room_of:
        room_status, room_of = solve_rooms(problem, starts, max(30.0, remaining), workers, None, on_progress)
    if not room_of:
        return Solution(
            placements={},
            status="INFEASIBLE",
            solve_seconds=time.monotonic() - started,
            failure={
                "stage": "rooms",
                "count": 1,
                "reasons": [
                    {
                        "rule": "H1",
                        "entity": "rooms",
                        "message": "The times found cannot all be given rooms; re-run, or add rooms.",
                    }
                ],
            },
        )

    placements = {key: Placement(start=starts[key], room_id=room_of[key]) for key in starts}
    violations = check(problem, placements)
    if violations:
        # Never hand back a timetable that breaks a hard rule.
        logger.error("Solver result failed validation: %s", violations[:5])
        return Solution(
            placements={},
            status="MODEL_INVALID",
            solve_seconds=time.monotonic() - started,
            failure={"stage": "validation", "count": len(violations), "reasons": [v.__dict__ for v in violations[:50]]},
        )

    scores = score(problem, placements)
    overall = "OPTIMAL" if status == "OPTIMAL" and room_status == "OPTIMAL" else "FEASIBLE"
    return Solution(
        placements=placements,
        status=overall,
        objective=weighted(problem, scores),
        soft_scores=scores,
        solve_seconds=round(time.monotonic() - started, 2),
    )
