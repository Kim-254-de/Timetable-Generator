"""
Exam solver benchmark at the size of the April 2026 timetable: about 1,500
papers over 8 days x 3 sessions (24 sessions), all modes and levels.

Until the real April 2026 data is supplied, the fixture is generated with the
same shape: ~350 class rows of 10-140 students, each sitting 7 papers, about
a third of papers shared by 2-4 class rows (common units, shared codes), a
few ODEL class rows, and ~70 rooms (exam seats = 0.9 x capacity).

    python -m tools.exam_benchmark [--seconds 300] [--workers 8] [--seed 7]
"""

from __future__ import annotations

import argparse
import random
import time
from datetime import date, timedelta

from app.exam_solver.model import ExamProblem, ExamRoom, Paper, Sitting
from app.exam_solver.solve import solve
from app.exam_solver.validate import check


def fixture(seed: int) -> ExamProblem:
    rng = random.Random(seed)  # noqa: S311 (a repeatable test fixture, not security)
    days = [d for d in (date(2026, 4, 8) + timedelta(days=i) for i in range(12)) if d.weekday() < 5][:8]
    rows = []
    for i in range(350):
        size = int(rng.choice([10, 15, 20, 25, 30, 35, 40, 50, 60, 80, 120]) * rng.uniform(0.8, 1.2))
        rows.append((f"R{i}", max(10, size), rng.random() < 0.05))
    need = {r[0]: 7 for r in rows}
    sizes = {r[0]: (r[1], r[2]) for r in rows}
    papers: list[Paper] = []
    n = 0
    ids = [r[0] for r in rows]
    while any(need.values()):
        open_rows = [r for r in ids if need[r] > 0]
        group = [rng.choice(open_rows)]
        if rng.random() < 0.33:
            # A shared paper: other class rows that still need papers.
            extra = rng.sample(open_rows, k=min(len(open_rows), rng.randint(1, 3)))
            group = list(dict.fromkeys(group + extra))
        for r in group:
            need[r] -= 1
        papers.append(Paper(id=f"P{n}", label=f"UNIT {n}", rows=tuple(Sitting(r, *sizes[r]) for r in group)))
        n += 1
    capacities = [40] * 20 + [60] * 15 + [100] * 15 + [120] * 10 + [200] * 6 + [300] * 4
    blocks = ["ADM", "STB", "TC", "UTC", "ED", "BS"]
    rooms = [
        ExamRoom(id=f"RM{i}", code=f"{blocks[i % 6]} {i}", block=blocks[i % 6], seats=int(c * 0.9))
        for i, c in enumerate(capacities)
    ]
    return ExamProblem(papers=papers, days=days, sessions=3, rooms=rooms)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    problem = fixture(args.seed)
    entries = sum(len(p.rows) for p in problem.papers)
    print(
        f"{len(problem.papers)} papers, {entries} class-row sittings, "
        f"{sum(p.students for p in problem.papers):,} student entries, {problem.slots} sessions, "
        f"{len(problem.rooms)} rooms / {problem.total_seats:,} exam seats"
    )
    started = time.monotonic()
    result = solve(problem, time_limit_s=args.seconds, workers=args.workers)
    took = time.monotonic() - started
    print(f"status {result.status} in {took:.1f}s; soft {result.soft_scores}")
    if result.failure:
        print("failure:", result.failure)
        return
    violations = check(problem, result.slots, result.seats)
    rooms_used = len({(result.slots[s.paper_id], s.room_id) for s in result.seats})
    print(f"{len(result.seats)} seats in {rooms_used} room-sessions; hard-rule violations: {len(violations)}")


if __name__ == "__main__":
    main()
