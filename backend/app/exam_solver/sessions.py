"""
Phase 1: each paper to one slot (a session of a day), with CP-SAT.

x[p, t] says paper p is in slot t (exactly one per paper; a pinned paper has
only its slot). Hard: H-E1 per class row and slot at most one paper; H-E2 per
class row and day at most two; H-E3 per slot the students fit all exam seats.
Soft: S-E1 back-to-back sessions, S-E2 two papers on a day, S-E3 big papers late.

When it is infeasible, it is solved again with one assumption per class row
and per slot's seats, to name the ones that cannot all hold.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ortools.sat.python import cp_model

from app.exam_solver.model import ExamProblem

STATUS = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}


class _Model:
    def __init__(self, problem: ExamProblem, families: bool):
        self.problem = problem
        self.m = cp_model.CpModel()
        self.families = families
        self.literals: dict[str, cp_model.IntVar] = {}
        self.x: dict[tuple[str, int], cp_model.IntVar] = {}
        self.penalties: list[Any] = []

    def family(self, name: str) -> cp_model.IntVar | None:
        if not self.families:
            return None
        if name not in self.literals:
            self.literals[name] = self.m.new_bool_var(name)
        return self.literals[name]

    def limit(self, terms: list[Any], cap: int, family: str) -> None:
        constraint = self.m.add(sum(terms) <= cap)
        lit = self.family(family)
        if lit is not None:
            constraint.only_enforce_if(lit)


def _build(problem: ExamProblem, families: bool) -> _Model:
    mm = _Model(problem, families)
    m, x = mm.m, mm.x
    slots = range(problem.slots)
    for p in problem.papers:
        allowed = [p.pinned] if p.pinned is not None else list(slots)
        for t in allowed:
            x[p.id, t] = m.new_bool_var(f"x[{p.id},{t}]")
        m.add_exactly_one(x[p.id, t] for t in allowed)
        if p.previous is not None and (p.id, p.previous) in x:
            m.add_hint(x[p.id, p.previous], 1)

    def at(paper_id: str, t: int) -> Any:
        return x.get((paper_id, t), 0)

    w = problem.weights
    for row, papers in problem.rows().items():
        if len(papers) < 2:
            continue
        ids = [p.id for p in papers]
        for t in slots:
            terms = [x[i, t] for i in ids if (i, t) in x]
            if len(terms) > 1:
                mm.limit(terms, 1, f"H-E1|{row}")
        for d in range(len(problem.days)):
            day_slots = range(d * problem.sessions, (d + 1) * problem.sessions)
            day_terms = [x[i, t] for i in ids for t in day_slots if (i, t) in x]
            if len(papers) > 2 and len(day_terms) > 2:
                mm.limit(day_terms, 2, f"H-E2|{row}")
            if families:
                continue
            if w.back_to_back:
                for s in range(problem.sessions - 1):
                    t = d * problem.sessions + s
                    now = [at(i, t) for i in ids]
                    nxt = [at(i, t + 1) for i in ids]
                    if any(not isinstance(v, int) for v in now) and any(not isinstance(v, int) for v in nxt):
                        b = m.new_bool_var(f"b2b[{row},{t}]")
                        m.add(sum(now) + sum(nxt) - 1 <= b)
                        mm.penalties.append(w.back_to_back * b)
            if w.same_day and len(day_terms) > 1:
                c = m.new_bool_var(f"day[{row},{d}]")
                m.add(sum(day_terms) - 1 <= c)
                mm.penalties.append(w.same_day * c)

    seats = problem.total_seats
    if sum(p.students for p in problem.papers) > seats:
        for t in slots:
            load = [p.students * x[p.id, t] for p in problem.papers if (p.id, t) in x]
            if load:
                mm.limit(load, seats, f"H-E3|{t}")
    if not families and w.big_late:
        for p in problem.papers:
            hundreds = (p.students + 99) // 100
            for t in slots:
                if (p.id, t) in x and problem.day_of(t):
                    mm.penalties.append(w.big_late * hundreds * problem.day_of(t) * x[p.id, t])
    if mm.penalties:
        m.minimize(sum(mm.penalties))
    return mm


def solve(problem: ExamProblem, time_limit_s: float, workers: int) -> tuple[str, dict[str, int], float | None]:
    mm = _build(problem, families=False)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(1.0, time_limit_s)
    solver.parameters.num_workers = workers
    status = solver.solve(mm.m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return STATUS.get(status, "UNKNOWN"), {}, None
    placed = {pid: t for (pid, t), v in mm.x.items() if solver.boolean_value(v)}
    return STATUS[status], placed, solver.objective_value


def explain(problem: ExamProblem, time_limit_s: float) -> list[dict[str, str]]:
    """The class rows and sessions whose rules can't all hold together."""
    mm = _build(problem, families=True)
    if not mm.literals:
        return []
    mm.m.add_assumptions(list(mm.literals.values()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(1.0, time_limit_s)
    solver.parameters.num_workers = 1
    if solver.solve(mm.m) != cp_model.INFEASIBLE:
        return []
    by_index = {v.index: name for name, v in mm.literals.items()}
    reasons: list[dict[str, str]] = []
    grouped: dict[str, list[str]] = defaultdict(list)
    for index in solver.sufficient_assumptions_for_infeasibility():
        rule, entity = by_index[index].split("|", 1)
        grouped[rule].append(entity)
    for rule, entities in grouped.items():
        for entity in entities[:20]:
            if rule == "H-E3":
                t = int(entity)
                day = problem.days[problem.day_of(t)]
                reasons.append(
                    {
                        "rule": rule,
                        "entity": f"{day:%a %d %b} session {problem.session_of(t) + 1}",
                        "message": (
                            f"The papers that must sit on {day:%a %d %b} session {problem.session_of(t) + 1} "
                            f"need more than the {problem.total_seats} exam seats."
                        ),
                    }
                )
            else:
                label = problem.row_label(entity)
                what = "one paper per session" if rule == "H-E1" else "at most 2 papers a day"
                reasons.append({"rule": rule, "entity": label, "message": f"{label}: its papers can't all fit {what}."})
    return reasons
