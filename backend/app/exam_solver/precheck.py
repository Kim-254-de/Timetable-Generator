"""What makes an exam timetable impossible before solving, in the Director's terms."""

from __future__ import annotations

from app.exam_solver.model import HEALTH, POSTGRADUATE, ExamProblem


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
    seats = problem.general_seats  # the health unit's rooms are for health papers only
    for p in problem.papers:
        if p.students > seats and not problem.is_health(p):
            add("H-E3", p.label, f"{p.label} has {p.students} students; all rooms together seat {seats}.")
        if p.pinned is not None and not 0 <= p.pinned < problem.slots:
            add("H-E4", p.label, f"{p.label} is pinned outside the exam period.")
    days = len(problem.days)
    for row, papers in problem.rows().items():
        label = problem.row_label(row)
        if len(papers) > 2 * days:
            add("H-E2", label, f"{label} sits {len(papers)} papers; at most 2 a day over {days} days is {2 * days}.")
    if problem.rules_on:
        edge = problem.edge_slots()
        first_last = "the first or last session of a day"
        for p in problem.papers:
            if p.pinned is not None and problem.edges_only(p) and 0 <= p.pinned < problem.slots and not problem.is_edge(p.pinned):
                add("H-E8", p.label, f"{p.label} is a {problem.category(p)} paper pinned outside {first_last}.")
            if p.pinned is not None and problem.first_week_only(p) and 0 <= p.pinned < problem.slots and not problem.in_first_week(p.pinned):
                add("H-E10", p.label, f"{p.label} is a postgraduate paper pinned outside the first week.")
        restricted = sum(p.students for p in problem.papers if problem.edges_only(p) and not problem.is_health(p))
        if restricted > seats * len(edge):
            message = f"{restricted} student entries must sit in {first_last}; those sessions seat {seats * len(edge)}."
            add("H-E8", "period", message)
        graduate = [p for p in problem.papers if problem.first_week_only(p)]
        week_edge = [t for t in edge if problem.in_first_week(t)]
        week_days = len({problem.day_of(t) for t in week_edge})
        per_day = min(2, len({problem.session_of(t) for t in edge}))
        for row, papers in problem.rows().items():
            count = sum(1 for p in papers if problem.first_week_only(p))
            if count > per_day * week_days:
                label = problem.row_label(row)
                message = f"{label} sits {count} postgraduate papers; the first week has room for {per_day * week_days} ({week_days} days, {per_day} a day)."
                add("H-E10", label, message)
        for health_unit, capacity in ((False, seats), (True, problem.health_seats)):
            entries = sum(p.students for p in graduate if problem.is_health(p) == health_unit)
            if capacity and entries > capacity * len(week_edge):
                message = f"{entries} postgraduate student entries must sit in the first week; its first and last sessions seat {capacity * len(week_edge)}."
                add("H-E10", "first week", message)
        health = [p for p in problem.papers if problem.category(p) == HEALTH and p.students]
        if health and not problem.health_seats:
            add("H-E9", "health unit", "No room open for exams is in the health unit: mark them under Venues in the admin console.")
        elif health:
            for p in health:
                if p.students > problem.health_seats:
                    add("H-E9", p.label, f"{p.label} has {p.students} students; the health unit seats {problem.health_seats}.")
            total = sum(p.students for p in health)
            if total > problem.health_seats * len(edge):
                message = f"{total} health student entries need more seats than the health unit has ({problem.health_seats * len(edge)})."
                add("H-E9", "health unit", message)
    for staff, papers in problem.invigilators().items():
        needed = sum(1 for p in papers if problem.category(p) != POSTGRADUATE)
        needed += 1 if needed < len(papers) else 0  # postgraduate papers can all share one room and session
        if needed > problem.slots:
            message = f"{staff} is the main invigilator of {needed} papers in separate sessions; the period has {problem.slots} slots."
            add("H-E7", staff, message)
    total = sum(p.students for p in problem.papers if not problem.is_health(p))
    if total > seats * problem.slots:
        add("H-E3", "period", f"{total} student entries need more seats than the period has ({seats * problem.slots}).")
    return findings
