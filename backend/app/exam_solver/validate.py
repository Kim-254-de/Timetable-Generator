"""Every hard-rule violation (H-E1 to H-E8) in an exam timetable and its seating."""

from __future__ import annotations

from collections import defaultdict

from app.exam_solver.model import ExamProblem, ExamViolation, Seat


def check(problem: ExamProblem, slots: dict[str, int], seats: list[Seat] | None = None) -> list[ExamViolation]:
    out: list[ExamViolation] = []
    papers = {p.id: p for p in problem.papers}

    def when(t: int) -> str:
        return f"{problem.days[problem.day_of(t)]:%a %d %b} session {problem.session_of(t) + 1}"

    for p in problem.papers:
        if p.id not in slots:
            out.append(ExamViolation("H-E4", f"{p.label} has no session.", (p.id,)))
            continue
        t = slots[p.id]
        if not 0 <= t < problem.slots:
            out.append(ExamViolation("H-E4", f"{p.label} is outside the exam period.", (p.id,)))
        elif p.pinned is not None and p.pinned != t:
            out.append(ExamViolation("H-E4", f"{p.label} is pinned and was moved.", (p.id,)))

    common_slots = problem.common_day_slots()
    for p in problem.papers:
        if slots.get(p.id) in common_slots and not problem.is_common(p):
            day = problem.days[problem.day_of(slots[p.id])]
            message = f"{p.label} isn't a common unit; {day:%a %d %b} is for common units only."
            out.append(ExamViolation("H-E8", message, (p.id,)))

    by_row_slot: dict[tuple[str, int], list[str]] = defaultdict(list)
    by_row_day: dict[tuple[str, int], list[str]] = defaultdict(list)
    load: dict[int, int] = defaultdict(int)
    for pid, t in slots.items():
        paper = papers.get(pid)
        if paper is None or not 0 <= t < problem.slots:
            continue
        load[t] += paper.students
        for r in paper.row_ids:
            by_row_slot[(r, t)].append(pid)
            by_row_day[(r, problem.day_of(t))].append(pid)
    by_staff_slot: dict[tuple[str, int], list[str]] = defaultdict(list)
    for pid, t in slots.items():
        paper = papers.get(pid)
        if paper is not None and paper.invigilator and 0 <= t < problem.slots:
            by_staff_slot[(paper.invigilator, t)].append(pid)
    for (staff, t), ids in by_staff_slot.items():
        if len(ids) > 1:
            labels = " and ".join(papers[i].label for i in ids)
            out.append(ExamViolation("H-E7", f"{staff} invigilates {labels} on {when(t)}.", tuple(ids)))
    for (r, t), ids in by_row_slot.items():
        if len(ids) > 1:
            out.append(
                ExamViolation("H-E1", f"{problem.row_label(r)} sits {len(ids)} papers on {when(t)}.", tuple(ids))
            )
    for (r, d), ids in by_row_day.items():
        if len(ids) > 2:
            out.append(
                ExamViolation(
                    "H-E2", f"{problem.row_label(r)} sits {len(ids)} papers on {problem.days[d]:%a %d %b}.", tuple(ids)
                )
            )
    for t, students in load.items():
        if students > problem.total_seats:
            out.append(
                ExamViolation("H-E3", f"{when(t)} has {students} students for {problem.total_seats} exam seats.")
            )

    if seats is not None:
        rooms = {r.id: r for r in problem.rooms}
        used: dict[tuple[str, int], int] = defaultdict(int)
        seated: dict[tuple[str, str], int] = defaultdict(int)
        kinds: dict[tuple[str, str], set[bool]] = defaultdict(set)
        odel = {(p.id, r.row_id): r.odel for p in problem.papers for r in p.rows}
        for s in seats:
            room = rooms.get(s.room_id)
            if room is None:
                out.append(
                    ExamViolation(
                        "H-E6", f"{papers[s.paper_id].label} sits in a room not open for exams.", (s.paper_id,)
                    )
                )
                continue
            used[(s.room_id, slots.get(s.paper_id, -1))] += s.students
            seated[(s.paper_id, s.row_id)] += s.students
            kinds[(s.paper_id, s.room_id)].add(odel.get((s.paper_id, s.row_id), False))
        for (room_id, t), students in used.items():
            if students > rooms[room_id].seats:
                out.append(
                    ExamViolation(
                        "H-E6",
                        f"{rooms[room_id].code} seats {students} on {when(t)}; "
                        f"it has {rooms[room_id].seats} exam seats.",
                    )
                )
        for p in problem.papers:
            for sitting in p.rows:
                if seated[(p.id, sitting.row_id)] != sitting.students:
                    out.append(
                        ExamViolation(
                            "H-E6",
                            f"{p.label}: {problem.row_label(sitting.row_id)} has {sitting.students} students, "
                            f"{seated[(p.id, sitting.row_id)]} seated.",
                            (p.id,),
                        )
                    )
        for (pid, room_id), mixed in kinds.items():
            if len(mixed) > 1:
                out.append(
                    ExamViolation(
                        "H-E6",
                        f"{papers[pid].label}: ODEL students share {rooms[room_id].code} with the others.",
                        (pid,),
                    )
                )
    return out
