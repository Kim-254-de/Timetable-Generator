"""
Benchmark: rebuild the Sep-Dec 2026 inputs from the hand-made timetable
(tests/fixtures/sep_dec_2026.json, made by tools.pdf_timetable), solve them
from scratch, and compare with the hand-made timetable on the same rules.

    python -m tools.benchmark [--time-limit 600] [--workers 8] [--out report.json]

The PDF has no room capacities, room types, class sizes, departments or
lecturer counts, so the benchmark states its assumptions instead of
inventing data:
- room size (H3) and type (H4) are not modelled: every room fits every class;
- a unit's department is its code prefix (COSC, LAWP ...), and a
  department's lecturer count (H9) is the most classes it runs at once in
  the hand-made timetable, so the hand-made timetable meets H9 by definition;
- each group is one printed class (unit + group label + the class rows
  listed together), with the meetings and lengths the PDF shows.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.solver import cpsat
from app.solver.model import DAYS, ClassRow, Placement, Problem, Room, Session, Weights, covered, slot
from app.solver.scoring import score
from app.solver.validate import check

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sep_dec_2026.json"


def building_of(room_code: str) -> str:
    match = re.match(r"([A-Z]+(?:-[A-Z]{2})?)", room_code)
    return match.group(1) if match else room_code


def build(data: dict[str, Any], weights: Weights | None = None) -> tuple[Problem, dict[str, Placement]]:
    rows = {label: ClassRow(id=f"r{i}", label=label) for i, label in enumerate(data["class_rows"])}
    room_codes = sorted({m["room"] for m in data["meetings"]})
    rooms = [Room(id=code, code=code, building=building_of(code), capacity=1, room_type="room") for code in room_codes]

    groups: dict[tuple[str, str | None, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for m in data["meetings"]:
        groups[(m["unit"], m["group"], tuple(m["class_rows"]))].append(m)

    prefixes = sorted({unit.split()[0] for unit, _g, _r in groups})
    dept_id = {p: i + 1 for i, p in enumerate(prefixes)}

    sessions: list[Session] = []
    handmade: dict[str, Placement] = {}
    for n, ((unit, group, class_rows), meetings) in enumerate(
        sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "", kv[0][2]))
    ):
        meetings.sort(key=lambda m: (DAYS.index(m["day"]), m["start_hour"]))
        for k, m in enumerate(meetings):
            key = f"g{n}-{k}"
            label = f"{unit}{' ' + group if group else ''} [{', '.join(class_rows)}]"
            sessions.append(
                Session(
                    key=key,
                    offering_id=f"{unit}|{n}",
                    group_id=f"g{n}",
                    index=k,
                    label=label,
                    department_id=dept_id[unit.split()[0]],
                    class_row_ids=tuple(rows[r].id for r in class_rows),
                    students=1,
                    length=m["length"],
                    room_type="room",
                )
            )
            handmade[key] = Placement(start=slot(DAYS.index(m["day"]), m["start_hour"]), room_id=m["room"])

    load: dict[tuple[int, int], int] = defaultdict(int)
    for s in sessions:
        for t in covered(handmade[s.key].start, s.length):
            load[(s.department_id, t)] += 1
    capacity = {d: 1 for d in dept_id.values()}
    for (d, _t), n_classes in load.items():
        capacity[d] = max(capacity[d], n_classes)

    problem = Problem(
        rooms=rooms,
        class_rows=list(rows.values()),
        sessions=sessions,
        department_capacity=capacity,
        weights=weights or Weights(),
    )
    return problem, handmade


def summarise(problem: Problem, placements: dict[str, Placement]) -> dict[str, Any]:
    violations = check(problem, placements)
    by_rule: dict[str, int] = defaultdict(int)
    for v in violations:
        by_rule[v.rule] += 1
    return {
        "hard_violations": dict(sorted(by_rule.items())),
        "soft": score(problem, placements),
        "examples": [v.message for v in violations[:10]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Solve the Sep-Dec 2026 benchmark and compare with the PDF.")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--time-limit", type=float, default=600)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    data = json.loads(args.fixture.read_text(encoding="utf-8"))
    problem, handmade = build(data)
    print(
        f"{len(problem.class_rows)} class rows, {len(problem.sessions)} sessions, {len(problem.rooms)} rooms, "
        f"{len(problem.department_capacity)} departments",
        file=sys.stderr,
    )

    # The hand-made timetable is scored against the parts of the rules it can be held to.
    report: dict[str, Any] = {
        "inputs": {
            "class_rows": len(problem.class_rows),
            "sessions": len(problem.sessions),
            "rooms": len(problem.rooms),
            "skipped_cells": len(data.get("skipped", [])),
        },
        "handmade": summarise(problem, handmade),
    }

    def progress(info: dict[str, object]) -> None:
        print(f"  {info['phase']}: objective {info['objective']:.0f} after {info['seconds']} s", file=sys.stderr)

    result = cpsat.solve(problem, time_limit_s=args.time_limit, workers=args.workers, on_progress=progress)
    report["solver"] = {"status": result.status, "seconds": result.solve_seconds, "failure": result.failure}
    if result.placements:
        report["solver"].update(summarise(problem, result.placements))

    text = json.dumps(report, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if result.placements else 1


if __name__ == "__main__":
    raise SystemExit(main())
