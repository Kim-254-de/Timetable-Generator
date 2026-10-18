from __future__ import annotations

import itertools

from app.solver import cpsat, precheck
from app.solver.groups import RowDemand, group_labels, propose
from app.solver.model import (
    ClassRow,
    Placement,
    Problem,
    Room,
    Session,
    Weights,
    slot,
    slot_hour,
)
from app.solver.scoring import score
from app.solver.validate import check


def _room(code: str, cap: int = 100, building: str = "STB", kind: str = "lecture_hall", **kw) -> Room:
    return Room(id=code, code=code, building=building, capacity=cap, room_type=kind, **kw)


def _session(
    key: str,
    rows: tuple[str, ...],
    length: int = 2,
    students: int = 50,
    dept: int = 1,
    offering: str | None = None,
    group: str | None = None,
    index: int = 0,
    **kw,
) -> Session:
    return Session(
        key=key,
        offering_id=offering or key,
        group_id=group or key,
        index=index,
        label=key,
        department_id=dept,
        class_row_ids=rows,
        students=students,
        length=length,
        room_type=kw.pop("room_type", "lecture_hall"),
        **kw,
    )


def _problem(sessions, rooms=None, rows=("R1", "R2"), capacity=None, weights=None) -> Problem:
    return Problem(
        rooms=rooms or [_room("STB 1"), _room("STB 2")],
        class_rows=[ClassRow(id=r, label=r) for r in rows],
        sessions=sessions,
        department_capacity=capacity or {1: 10, 2: 10},
        weights=weights or Weights(),
    )


def test_feasible_small_timetable_has_no_hard_violations():
    sessions = [_session(f"U{i}", ("R1",) if i % 2 else ("R2",)) for i in range(8)]
    sessions.append(_session("SHARED", ("R1", "R2")))
    problem = _problem(sessions)
    result = cpsat.solve(problem, time_limit_s=20, workers=4)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert check(problem, result.placements) == []
    assert len(result.placements) == 9


def test_class_row_never_double_booked_and_rooms_respected():
    # 30 two-hour sessions for one row = all 60 hours: forces a dense, exact packing.
    sessions = [_session(f"U{i}", ("R1",)) for i in range(30)]
    problem = _problem(
        sessions, rooms=[_room("A")], rows=("R1",), weights=Weights(gaps=0, same_day=0, long_day=0, edge_hours=0)
    )
    result = cpsat.solve(problem, time_limit_s=30, workers=4)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert check(problem, result.placements) == []


def test_room_capacity_and_type():
    sessions = [
        _session("BIG", ("R1",), students=300),
        _session("LAB", ("R2",), students=20, room_type="lab"),
    ]
    rooms = [_room("HALL", 400), _room("SMALL", 50), _room("LAB 1", 30, kind="lab")]
    problem = _problem(sessions, rooms=rooms)
    result = cpsat.solve(problem, time_limit_s=10, workers=2)
    assert result.placements["BIG"].room_id == "HALL"
    assert result.placements["LAB"].room_id == "LAB 1"


def test_split_row_groups_rotate_through_one_lab():
    # One class row split into four lab groups of one unit, and a single lab:
    # the groups take turns, and the row's lecture keeps clear of all of them.
    labs = [_session(f"LAB-{g}", ("R1",), offering="SMED100", group=g, students=30, room_type="lab") for g in "ABCD"]
    lecture = _session("MATH", ("R1",))
    problem = _problem([*labs, lecture], rooms=[_room("STB 1"), _room("LAB 1", 40, kind="lab")])
    result = cpsat.solve(problem, time_limit_s=10, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert check(problem, result.placements) == []
    lab_hours = {
        t for g in "ABCD" for t in range(result.placements[f"LAB-{g}"].start, result.placements[f"LAB-{g}"].start + 2)
    }
    math = result.placements["MATH"].start
    assert not lab_hours & {math, math + 1}


def test_split_row_groups_may_share_an_hour():
    a = _session("COSC103-A", ("R1",), offering="COSC103", group="A", students=80)
    b = _session("COSC103-B", ("R1",), offering="COSC103", group="B", students=80)
    problem = _problem([a, b])
    together = {"COSC103-A": Placement(slot(1, 10), "STB 1"), "COSC103-B": Placement(slot(1, 10), "STB 2")}
    assert check(problem, together) == []
    same_group = _problem([a, _session("COSC103-A2", ("R1",), offering="COSC103", group="A", index=1)])
    clash = {"COSC103-A": Placement(slot(1, 10), "STB 1"), "COSC103-A2": Placement(slot(1, 10), "STB 2")}
    assert {v.rule for v in check(same_group, clash)} == {"H2"}


def test_department_capacity_limits_parallel_classes():
    sessions = [_session(f"U{i}", (f"R{i}",), dept=1) for i in range(3)]
    problem = _problem(sessions, rooms=[_room(f"X{i}") for i in range(3)], rows=("R0", "R1", "R2"), capacity={1: 1})
    result = cpsat.solve(problem, time_limit_s=10, workers=2)
    starts = sorted(p.start for p in result.placements.values())
    assert all(b - a >= 2 or (b // 12 != a // 12) for a, b in itertools.pairwise(starts))
    assert check(problem, result.placements) == []


def test_pinned_session_stays_put():
    pin = Placement(start=slot(2, 10), room_id="STB 2")
    sessions = [_session("PINNED", ("R1",), pinned=pin), _session("OTHER", ("R1",))]
    result = cpsat.solve(_problem(sessions), time_limit_s=10, workers=2)
    assert result.placements["PINNED"] == pin


def test_unavailable_hours_are_avoided():
    blocked = frozenset(t for t in range(60) if slot_hour(t) < 17)  # only 17:00-19:00 free
    rows = [ClassRow(id="R1", label="R1", unavailable=blocked)]
    problem = Problem(
        rooms=[_room("A")], class_rows=rows, sessions=[_session("U", ("R1",))], department_capacity={1: 5}
    )
    result = cpsat.solve(problem, time_limit_s=10, workers=2)
    assert slot_hour(result.placements["U"].start) == 17


def test_soft_constraints_prefer_mid_day_and_spread():
    a = _session("G#1", ("R1",), offering="G", group="G", index=0)
    b = _session("G#2", ("R1",), offering="G", group="G", index=1)
    result = cpsat.solve(_problem([a, b]), time_limit_s=10, workers=2)
    pa, pb = result.placements["G#1"], result.placements["G#2"]
    assert pa.start // 12 != pb.start // 12  # S2 different days
    assert slot_hour(pa.start) >= 8 and slot_hour(pa.start) + 2 <= 17  # S4 avoids 07:00 and late
    assert result.soft_scores["edge_hours"] == 0


def test_repair_keeps_sessions_and_lecturers_clear():
    prev_a = Placement(start=slot(0, 10), room_id="STB 1")
    prev_b = Placement(start=slot(1, 10), room_id="STB 1")
    a = _session("A", ("R1",), previous=prev_a, lecturer_id="L1")
    b = _session("B", ("R2",), previous=prev_b, lecturer_id="L1")
    c = _session("C", ("R2",), pinned=Placement(start=slot(1, 10), room_id="STB 2"))  # takes B's slot for R2
    problem = _problem([a, b, c])
    result = cpsat.solve(problem, time_limit_s=10, workers=2)
    assert result.placements["A"] == prev_a  # unaffected, kept (S8)
    assert result.placements["B"] != prev_b  # had to move
    assert check(problem, result.placements) == []  # and lecturer L1 isn't double-booked (H13)
    assert result.soft_scores["moved"] == 1


def test_precheck_names_the_overloaded_class_row():
    sessions = [_session(f"U{i}", ("R1",), length=3) for i in range(21)]  # 63 h > 60
    result = cpsat.solve(_problem(sessions, rows=("R1",)), time_limit_s=5, workers=1)
    assert result.status == "INFEASIBLE"
    assert result.failure["stage"] == "precheck"
    assert any(r["rule"] == "H2" and r["entity"] == "R1" for r in result.failure["reasons"])


def test_precheck_reports_missing_room_size():
    result = cpsat.solve(_problem([_session("HUGE", ("R1",), students=900)]), time_limit_s=5, workers=1)
    assert result.failure["reasons"][0]["rule"] == "H3"


def test_solver_infeasibility_is_explained():
    # Two class rows need 63 hours of a room that has 60.
    rooms = [_room("ONLY", 100)]
    sessions = [_session(f"A{i}", ("R1",), length=3) for i in range(10)]
    sessions += [_session(f"B{i}", ("R2",), length=3) for i in range(11)]
    problem = _problem(sessions, rooms=rooms)
    findings = precheck.run(problem)
    assert any(f.rule == "H1" for f in findings)  # caught early, by the room-hours count
    result = cpsat.solve(problem, time_limit_s=10, workers=2)
    assert result.status == "INFEASIBLE"


def test_core_explanation_from_assumptions():
    # Pre-checks pass (enough hours overall), but the pins make R1 impossible.
    pins = [Placement(start=slot(0, 8), room_id="STB 1"), Placement(start=slot(0, 9), room_id="STB 2")]
    sessions = [_session("P1", ("R1",), pinned=pins[0]), _session("P2", ("R1",), pinned=pins[1])]
    result = cpsat.solve(_problem(sessions), time_limit_s=10, workers=2)
    assert result.status == "INFEASIBLE"
    assert result.failure["stage"] == "time"
    assert any(r["rule"] == "H2" and r["entity"] == "R1" for r in result.failure["reasons"])


def test_validator_catches_each_rule():
    rooms = [_room("A", 30), _room("LAB", 30, kind="lab")]
    sessions = [
        _session("X", ("R1",), students=50),
        _session("Y", ("R1",), lecturer_id="L"),
        _session("Z", ("R2",), lecturer_id="L", room_type="lab"),
    ]
    problem = _problem(sessions, rooms=rooms, capacity={1: 1})
    placements = {"X": Placement(slot(0, 8), "A"), "Y": Placement(slot(0, 8), "A"), "Z": Placement(slot(0, 8), "A")}
    rules = {v.rule for v in check(problem, placements)}
    assert {"H1", "H2", "H3", "H4", "H9", "H13"} <= rules
    assert {v.rule for v in check(problem, {})} == {"H5"}
    assert "H6" in {v.rule for v in check(problem, {**placements, "X": Placement(slot(0, 18), "A")})}


def test_scoring_counts_gaps_and_edges():
    sessions = [_session("A", ("R1",), length=1), _session("B", ("R1",), length=1)]
    problem = _problem(sessions)
    placements = {"A": Placement(slot(0, 7), "STB 1"), "B": Placement(slot(0, 9), "STB 1")}
    scores = score(problem, placements)
    assert scores["gaps"] == 1
    assert scores["early_starts"] == 1
    assert scores["edge_hours"] == 1


def test_group_proposal():
    rows = [RowDemand("a", "BED Y1S1", 300), RowDemand("b", "BSC Y1S1", 90), RowDemand("c", "BA Y1S1", 60)]
    groups = propose(rows, largest_room=150)
    assert all(g.students <= 150 for g in groups)
    assert sum(g.students for g in groups) == 450
    assert [g.label for g in groups][:2] == ["GR A", "GR B"]
    split = [g for g in groups if any(m[0] == "a" for m in g.members)]
    assert len(split) == 2  # the 300-student row is split into two parallel groups
    assert propose([RowDemand("x", "X", 40)], 100)[0].label == ""
    assert group_labels(28)[-2:] == ["GR AA", "GR AB"]
