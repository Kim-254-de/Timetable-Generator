"""
Phase 1: each paper to one slot (a session of a day), with CP-SAT.

x[p, t] says paper p is in slot t (exactly one per paper; a pinned paper has
only its slot). Hard: H-E1 per class row and slot at most one paper; H-E2 per
class row and day at most two; H-E3 per slot the students fit all exam seats;
H-E8 only common papers on the second day (the others get no slot there).
Soft: S-E1 back-to-back sessions, S-E2 two papers on a day, S-E3 big papers late,
S-E4 a guessed class (papers with no students known) one paper a session and
two a day, S-E5 papers with no students known spread over the period, S-E6
each common paper not on the second day (by its hundreds of students).

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
    common_slots = set(problem.common_day_slots())
    common = {p.id for p in problem.papers if common_slots and problem.is_common(p)}
    for p in problem.papers:
        if p.pinned is not None:
            allowed = [p.pinned]
        elif p.id in common:
            allowed = list(slots)
        else:
            allowed = [t for t in slots if t not in common_slots]
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

    # H-E7: one main invigilator, one paper per slot.
    for staff, papers in problem.invigilators().items():
        if len(papers) < 2:
            continue
        for t in slots:
            terms = [x[p.id, t] for p in papers if (p.id, t) in x]
            if len(terms) > 1:
                mm.limit(terms, 1, f"H-E7|{staff}")

    seats = problem.total_seats
    if sum(p.students for p in problem.papers) > seats:
        for t in slots:
            load = [p.students * x[p.id, t] for p in problem.papers if (p.id, t) in x]
            if load:
                mm.limit(load, seats, f"H-E3|{t}")
    if not families:
        _guesses(mm, problem, common_slots)
        # S-E6: per common paper not on the second day, by its hundreds of students: the biggest stay there.
        for p in problem.papers:
            if p.id in common:
                on_day = [x[p.id, t] for t in common_slots if (p.id, t) in x]
                hundreds = max(1, (p.students + 99) // 100)
                mm.penalties.append(w.common_day * hundreds * (1 - sum(on_day)))
    if not families and w.big_late:
        for p in problem.papers:
            hundreds = (p.students + 99) // 100
            for t in slots:
                if (p.id, t) in x and problem.day_of(t):
                    mm.penalties.append(w.big_late * hundreds * problem.day_of(t) * x[p.id, t])
    if mm.penalties:
        m.minimize(sum(mm.penalties))
    return mm


def _guesses(mm: _Model, problem: ExamProblem, common_slots: set[int]) -> None:
    """S-E4 and S-E5, for papers nobody is known to sit: soft, so a wrong guess can't make it infeasible."""
    m, x, w = mm.m, mm.x, problem.weights
    slots = range(problem.slots)
    for group, papers in problem.guessed_classes().items():
        if len(papers) < 2:
            continue
        for t in slots:
            terms = [x[p.id, t] for p in papers if (p.id, t) in x]
            if len(terms) > 1 and w.guessed_clash:
                over = m.new_int_var(0, len(terms), f"guess[{group},{t}]")
                m.add(sum(terms) - 1 <= over)
                mm.penalties.append(w.guessed_clash * over)
        for d in range(len(problem.days)):
            day = range(d * problem.sessions, (d + 1) * problem.sessions)
            terms = [x[p.id, t] for p in papers for t in day if (p.id, t) in x]
            if len(terms) > 2 and w.guessed_day:
                over = m.new_int_var(0, len(terms), f"guessday[{group},{d}]")
                m.add(sum(terms) - 2 <= over)
                mm.penalties.append(w.guessed_day * over)
    # The second day is for common papers: the others spread over the rest of the period.
    unknown = [p for p in problem.papers if p.unknown_students and not (common_slots and problem.is_common(p))]
    open_slots = problem.slots - len(common_slots)
    if len(unknown) > 1 and open_slots > 0 and w.spread:
        share = -(-len(unknown) // open_slots)  # an even share of the sessions, rounded up
        for t in slots:
            terms = [x[p.id, t] for p in unknown if (p.id, t) in x]
            if len(terms) > share:
                over = m.new_int_var(0, len(terms), f"spread[{t}]")
                m.add(sum(terms) - share <= over)
                mm.penalties.append(w.spread * over)


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
                if rule == "H-E7":
                    message = f"{entity}: their papers can't each have a session."
                    reasons.append({"rule": rule, "entity": entity, "message": message})
                    continue
                label = problem.row_label(entity)
                what = "one paper per session" if rule == "H-E1" else "at most 2 papers a day"
                reasons.append({"rule": rule, "entity": label, "message": f"{label}: its papers can't all fit {what}."})
    return reasons
