"""Both phases: the best exam timetable within the time limit, or why there is none."""

from __future__ import annotations

import itertools
import time
from collections import defaultdict

from app.exam_solver import precheck, rooms, sessions
from app.exam_solver.model import COMMON, POSTGRADUATE, ExamProblem, ExamSolution, Paper, Seat
from app.exam_solver.validate import check


def soft_scores(problem: ExamProblem, slots: dict[str, int], seats: list[Seat] | None = None) -> dict[str, float]:
    """S-E1 back-to-back class rows, S-E2 two papers a day, S-E3 student-days into the period, S-E4, S-E7, S-E8."""
    taken: dict[str, set[int]] = defaultdict(set)
    for p in problem.papers:
        if p.id in slots:
            for r in p.row_ids:
                taken[r].add(slots[p.id])
    back_to_back = same_day = 0
    for used in taken.values():
        by_day: dict[int, list[int]] = defaultdict(list)
        for t in used:
            by_day[problem.day_of(t)].append(problem.session_of(t))
        for day_sessions in by_day.values():
            day_sessions.sort()
            if len(day_sessions) > 1:
                same_day += 1
            back_to_back += sum(1 for a, b in itertools.pairwise(day_sessions) if b == a + 1)
    late = sum(p.students * problem.day_of(slots[p.id]) for p in problem.papers if p.id in slots)
    # S-E4: papers nobody is known to sit that share a guessed class and a session.
    guessed = 0
    for papers in problem.guessed_classes().values():
        per_slot: dict[int, int] = defaultdict(int)
        for p in papers:
            if p.id in slots:
                per_slot[slots[p.id]] += 1
        guessed += sum(n - 1 for n in per_slot.values() if n > 1)
    # S-E7: common papers on the busiest day.
    per_day: dict[int, int] = defaultdict(int)
    for p in problem.papers:
        if p.id in slots and problem.category(p) == COMMON:
            per_day[problem.day_of(slots[p.id])] += 1
    # S-E8: rooms beyond one for a session's postgraduate papers.
    graduate_rooms: dict[int, set[str]] = defaultdict(set)
    kinds = {p.id: problem.category(p) for p in problem.papers}
    for s in seats or []:
        if kinds.get(s.paper_id) == POSTGRADUATE and s.paper_id in slots:
            graduate_rooms[slots[s.paper_id]].add(s.room_id)
    return {
        "back_to_back": back_to_back,
        "same_day": same_day,
        "student_days": late,
        "guessed_clashes": guessed,
        "common_busiest_day": max(per_day.values(), default=0),
        "postgraduate_extra_rooms": sum(len(rooms_) - 1 for rooms_ in graduate_rooms.values()),
        # S-E9: papers common by their numbers that had to sit outside the first and last sessions.
        "common_by_numbers_midday": sum(
            1
            for p in problem.papers
            if p.id in slots and problem.common_by_numbers(p) and not problem.is_edge(slots[p.id])
        ),
    }


def seat_all(problem: ExamProblem, slots: dict[str, int]) -> list[Seat]:
    by_slot: dict[int, list[Paper]] = defaultdict(list)
    for p in problem.papers:
        if p.id in slots:
            by_slot[slots[p.id]].append(p)
    out: list[Seat] = []
    for t in sorted(by_slot):
        out.extend(rooms.seat_session(by_slot[t], problem.rooms))
    return out


def solve(problem: ExamProblem, time_limit_s: float = 300, workers: int = 8) -> ExamSolution:
    started = time.monotonic()
    findings = precheck.run(problem)
    if findings:
        return ExamSolution(
            slots={},
            seats=[],
            status="INFEASIBLE",
            solve_seconds=time.monotonic() - started,
            failure={"stage": "precheck", "reasons": findings[:50], "count": len(findings)},
        )
    status, slots, _objective = sessions.solve(problem, time_limit_s * 0.9, workers)
    if not slots:
        reasons = (
            sessions.explain(problem, min(60.0, time_limit_s / 2))
            if status == "INFEASIBLE"
            else [
                {
                    "rule": "?",
                    "entity": "time limit",
                    "message": "No timetable found in the time limit; allow more time.",
                }
            ]
        )
        return ExamSolution(
            slots={},
            seats=[],
            status=status,
            solve_seconds=time.monotonic() - started,
            failure={
                "stage": "sessions",
                "reasons": reasons or [{"rule": "?", "entity": "", "message": "The rules can't all hold."}],
                "count": len(reasons),
            },
        )
    try:
        seats = seat_all(problem, slots)
    except rooms.SeatingError as exc:
        return ExamSolution(
            slots=slots,
            seats=[],
            status="INFEASIBLE",
            solve_seconds=time.monotonic() - started,
            failure={"stage": "rooms", "reasons": [{"rule": "H-E6", "entity": "", "message": str(exc)}], "count": 1},
        )
    violations = check(problem, slots, seats)
    if violations:  # never expected: both phases keep the rules
        return ExamSolution(
            slots={},
            seats=[],
            status="INVALID",
            solve_seconds=time.monotonic() - started,
            failure={"stage": "validate", "reasons": [v.__dict__ for v in violations[:50]], "count": len(violations)},
        )
    return ExamSolution(
        slots=slots,
        seats=seats,
        status=status,
        soft_scores=soft_scores(problem, slots, seats),
        solve_seconds=time.monotonic() - started,
    )
