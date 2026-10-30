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
    for row, papers in problem.rows().items():
        if len(papers) > 2 * days:
            label = problem.row_label(row)
            add("H-E2", label, f"{label} sits {len(papers)} papers; at most 2 a day over {days} days is {2 * days}.")
    for staff, papers in problem.invigilators().items():
        if len(papers) > problem.slots:
            message = f"{staff} is the main invigilator of {len(papers)} papers; the period has {problem.slots} slots."
            add("H-E7", staff, message)
    total = sum(p.students for p in problem.papers)
    if total > seats * problem.slots:
        add("H-E3", "period", f"{total} student entries need more seats than the period has ({seats * problem.slots}).")
    return findings
