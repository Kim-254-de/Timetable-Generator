"""What makes an exam timetable impossible before solving, in the Director's terms."""

from __future__ import annotations

from app.exam_solver.model import ExamProblem


def run(problem: ExamProblem) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def add(rule: str, entity: str, message: str) -> None:
        findings.append({"rule": rule, "entity": entity, "message": message})

    if problem.slots == 0:
        add("H-E4", "exam period", "Set the exam period: its dates, weekdays and sessions.")
        return findings
    if not problem.rooms:
        add("H-E3", "rooms", "No room is available for exams.")
        return findings
    seats = problem.total_seats
    for p in problem.papers:
        if p.students > seats:
            add("H-E3", p.label, f"{p.label} has {p.students} students; all rooms together seat {seats}.")
        if p.pinned is not None and not 0 <= p.pinned < problem.slots:
            add("H-E4", p.label, f"{p.label} is pinned outside the exam period.")
    days = len(problem.days)
    common_slots = problem.common_day_slots()
    for row, papers in problem.rows().items():
        label = problem.row_label(row)
        if len(papers) > 2 * days:
            add("H-E2", label, f"{label} sits {len(papers)} papers; at most 2 a day over {days} days is {2 * days}.")
            continue
        others = sum(1 for p in papers if not problem.is_common(p)) if common_slots else 0
        if others > 2 * (days - 1):
            message = (
                f"{label} sits {others} papers that aren't common units; the second day is for common units, "
                f"and at most 2 a day over the other {days - 1} days is {2 * (days - 1)}."
            )
            add("H-E8", label, message)
    if common_slots:
        day = problem.days[problem.common_day or 0]
        for p in problem.papers:
            if p.pinned in common_slots and not problem.is_common(p):
                add("H-E8", p.label, f"{p.label} is pinned on {day:%a %d %b}, the day for common units only.")
    for staff, papers in problem.invigilators().items():
        if len(papers) > problem.slots:
            message = f"{staff} is the main invigilator of {len(papers)} papers; the period has {problem.slots} slots."
            add("H-E7", staff, message)
    total = sum(p.students for p in problem.papers)
    if total > seats * problem.slots:
        add("H-E3", "period", f"{total} student entries need more seats than the period has ({seats * problem.slots}).")
    return findings
