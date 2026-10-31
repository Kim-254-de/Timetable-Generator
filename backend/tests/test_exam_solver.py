from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from app.exam_solver import rooms as seating
from app.exam_solver import sessions
from app.exam_solver.model import ExamProblem, ExamRoom, Paper, Sitting
from app.exam_solver.solve import solve
from app.exam_solver.validate import check

DAYS = [date(2026, 11, 23) + timedelta(days=i) for i in range(5)]  # Mon-Fri


def _room(code: str, seats: int, block: str = "STB") -> ExamRoom:
    return ExamRoom(id=code, code=code, block=block, seats=seats)


def _paper(pid: str, *rows: tuple[str, int] | tuple[str, int, bool], pinned: int | None = None) -> Paper:
    return Paper(id=pid, label=pid, rows=tuple(Sitting(*r) for r in rows), pinned=pinned)


def test_class_rows_never_clash_or_sit_more_than_two_a_day():
    papers = [_paper(f"P{i}", ("R1", 50), ("R2" if i % 2 else "R3", 30)) for i in range(8)]
    problem = ExamProblem(papers=papers, days=DAYS[:4], sessions=3, rooms=[_room("A", 200), _room("B", 200)])
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert check(problem, result.slots, result.seats) == []
    per_day = defaultdict(int)
    for t in result.slots.values():
        per_day[problem.day_of(t)] += 1
    assert max(per_day.values()) <= 2  # R1 sits every paper


def test_back_to_back_sessions_are_avoided_when_there_is_room():
    papers = [_paper(f"P{i}", ("R1", 40)) for i in range(4)]
    problem = ExamProblem(papers=papers, days=DAYS[:2], sessions=3, rooms=[_room("A", 100)])
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.soft_scores["back_to_back"] == 0  # two a day, at 8:30 and 14:30


def test_small_papers_share_a_room_within_its_seats():
    papers = [_paper("SMALL", ("R1", 20)), _paper("MID", ("R2", 80))]
    placed = seating.seat_session(papers, [_room("ADM 1", 100), _room("UTC 1", 150, "UTC")])
    assert {s.room_id for s in placed} == {"ADM 1"}


def test_a_big_paper_is_split_over_rooms_in_one_block():
    papers = [_paper("BIG", ("R1", 150), ("R2", 140), ("R3", 60))]
    rooms = [_room("STB 1", 160), _room("STB 2", 160), _room("UTC 1", 160, "UTC"), _room("STB 3", 100)]
    placed = seating.seat_session(papers, rooms)
    assert {s.room_id for s in placed} <= {"STB 1", "STB 2", "STB 3"}
    assert len({(s.row_id, s.room_id) for s in placed}) == 3  # each class row sits in one room


def test_odel_sits_apart_from_the_rest_of_its_paper():
    papers = [_paper("P", ("R1", 30), ("R1-ODEL", 10, True))]
    placed = seating.seat_session(papers, [_room("A", 100), _room("B", 100)])
    rooms = {s.row_id: s.room_id for s in placed}
    assert rooms["R1"] != rooms["R1-ODEL"]


def test_a_class_row_bigger_than_every_room_is_split_into_parts():
    placed = seating.seat_session([_paper("P", ("HUGE", 250))], [_room("A", 100), _room("B", 100), _room("C", 100)])
    assert sorted((s.part, s.parts, s.students) for s in placed) == [(1, 3, 84), (2, 3, 83), (3, 3, 83)]
    assert len({s.room_id for s in placed}) == 3


def test_a_pinned_paper_stays():
    papers = [_paper("A", ("R1", 10), pinned=4), _paper("B", ("R1", 10))]
    problem = ExamProblem(papers=papers, days=DAYS[:2], sessions=3, rooms=[_room("A", 50)])
    result = solve(problem, time_limit_s=10, workers=2)
    assert result.slots["A"] == 4 and result.slots["B"] != 4


def test_the_precheck_names_a_row_with_too_many_papers():
    papers = [_paper(f"P{i}", ("R1", 10)) for i in range(5)]
    problem = ExamProblem(
        papers=papers, days=DAYS[:2], sessions=3, rooms=[_room("A", 50)], row_labels={"R1": "BSC Y1S1"}
    )
    result = solve(problem, time_limit_s=10, workers=2)
    assert result.failure and result.failure["stage"] == "precheck"
    assert "BSC Y1S1 sits 5 papers" in result.failure["reasons"][0]["message"]


def test_an_impossible_session_is_explained():
    # Two big papers pinned to the same session can't both fit the seats.
    papers = [_paper("A", ("R1", 80), pinned=0), _paper("B", ("R2", 80), pinned=0)]
    problem = ExamProblem(papers=papers, days=DAYS[:1], sessions=2, rooms=[_room("A", 100)])
    status, slots, _ = sessions.solve(problem, 5, 1)
    assert status == "INFEASIBLE" and slots == {}
    reasons = sessions.explain(problem, 5)
    assert reasons and reasons[0]["rule"] == "H-E3"


def test_a_main_invigilator_named_before_generating_has_one_paper_per_slot():
    # Three papers of different classes, all with Dr. Otieno as main invigilator; a day of three sessions.
    papers = [Paper(id=f"P{i}", label=f"P{i}", rows=(Sitting(f"R{i}", 30),), invigilator="STF/0001") for i in range(3)]
    problem = ExamProblem(papers=papers, days=DAYS[:1], sessions=3, rooms=[_room("A", 200)])
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert sorted(result.slots.values()) == [0, 1, 2]
    assert check(problem, result.slots, result.seats) == []
    clash = check(problem, {"P0": 0, "P1": 0, "P2": 1})
    assert [v.rule for v in clash] == ["H-E7"] and "STF/0001 invigilates P0 and P1" in clash[0].message


def test_a_paper_nobody_is_known_to_sit_gets_a_slot_and_no_room():
    papers = [_paper("SEATED", ("R1", 40)), Paper(id="NOBODY", label="NOBODY", rows=())]
    problem = ExamProblem(papers=papers, days=DAYS[:1], sessions=2, rooms=[_room("A", 100)])
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert set(result.slots) == {"SEATED", "NOBODY"}
    assert [s.paper_id for s in result.seats] == ["SEATED"]
    assert check(problem, result.slots, result.seats) == []


def test_the_class_is_guessed_from_the_code():
    from app.exam_solver.model import guessed_class

    assert guessed_class("BPPA 110") == "BPPA year 1"
    assert guessed_class("bppa221") == "BPPA year 2"
    assert guessed_class("COSC 0172") == "COSC year 1"
    assert guessed_class("Math 446") == "MATH year 4"
    assert guessed_class("123") is None


def test_papers_nobody_is_known_to_sit_are_spread_and_their_guessed_classes_kept_apart():
    # A department's whole list with no students known yet: four papers per year of BPPA, years 1-3.
    papers = [
        Paper(id=f"BPPA {y}1{i}", label=f"BPPA {y}1{i}", rows=(), codes=(f"BPPA {y}1{i}",))
        for y in (1, 2, 3)
        for i in range(4)
    ]
    problem = ExamProblem(papers=papers, days=DAYS[:2], sessions=3, rooms=[_room("A", 100)])
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    per_slot = defaultdict(int)
    for t in result.slots.values():
        per_slot[t] += 1
    assert max(per_slot.values()) == 2  # 12 papers over 6 sessions: an even share, not all in one
    for year in (1, 2, 3):
        mine = [result.slots[f"BPPA {year}1{i}"] for i in range(4)]
        assert len(set(mine)) == 4  # one paper of the year a session
        by_day = defaultdict(int)
        for t in mine:
            by_day[problem.day_of(t)] += 1
        assert max(by_day.values()) <= 2
    assert result.soft_scores["guessed_clashes"] == 0
    assert check(problem, result.slots, result.seats) == []


def test_a_guess_never_makes_the_timetable_impossible():
    # Five year-1 papers but only three sessions: the guess gives way.
    papers = [Paper(id=f"P{i}", label=f"P{i}", rows=(), codes=(f"BPPA 11{i}",)) for i in range(5)]
    problem = ExamProblem(papers=papers, days=DAYS[:1], sessions=3, rooms=[_room("A", 100)])
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert len(set(result.slots.values())) == 3


def _common_problem(papers: list[Paper], days: int = 3) -> ExamProblem:
    programmes = {"BIT1": "BIT", "BIT2": "BIT", "BSC1": "BSC", "BED1": "BED", "BCOM1": "BCOM"}
    return ExamProblem(
        papers=papers,
        days=DAYS[:days],
        sessions=3,
        rooms=[_room("A", 400), _room("B", 400)],
        row_programmes=programmes,
    )


def test_common_units_are_all_sat_on_the_second_day_and_nothing_else_is():
    papers = [
        _paper("COMS 101", ("BIT1", 120), ("BSC1", 90), ("BED1", 200)),  # three programmes: common
        _paper("UCU 102", ("BIT1", 120), ("BCOM1", 150)),
        Paper(id="BITE 131/COSC 130", label="BITE 131/COSC 130", rows=(), codes=("BITE 131", "COSC 130")),
        _paper("BIT 110", ("BIT1", 120)),  # one programme, two of its class rows: not common
        _paper("BIT 111", ("BIT1", 120), ("BIT2", 40)),
        _paper("BSC 110", ("BSC1", 90)),
        Paper(id="BPPA 110", label="BPPA 110", rows=(), codes=("BPPA 110",)),
    ]
    problem = _common_problem(papers)
    assert [p.id for p in papers if problem.is_common(p)] == ["COMS 101", "UCU 102", "BITE 131/COSC 130"]
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    on_day_two = {pid for pid, t in result.slots.items() if problem.day_of(t) == 1}
    assert on_day_two == {"COMS 101", "UCU 102", "BITE 131/COSC 130"}
    assert result.soft_scores["common_elsewhere"] == 0
    assert check(problem, result.slots, result.seats) == []


def test_a_common_unit_the_second_day_cant_hold_goes_to_another_day():
    # BIT1 sits three common papers: at most two a day, so one is left for another day.
    papers = [_paper(f"C{i}", ("BIT1", 50), ("BSC1", 50)) for i in range(3)] + [_paper("BIT 110", ("BIT1", 50))]
    problem = _common_problem(papers)
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert sum(1 for i in range(3) if problem.day_of(result.slots[f"C{i}"]) == 1) == 2
    assert problem.day_of(result.slots["BIT 110"]) != 1
    assert result.soft_scores["common_elsewhere"] == 1
    assert check(problem, result.slots, result.seats) == []


def test_only_common_units_may_be_moved_or_pinned_onto_the_second_day():
    papers = [_paper("COMS 101", ("BIT1", 50), ("BSC1", 50)), _paper("BIT 110", ("BIT1", 50))]
    problem = _common_problem(papers)
    broken = check(problem, {"COMS 101": 3, "BIT 110": 4})
    assert [v.rule for v in broken] == ["H-E8"] and "BIT 110 isn't a common unit" in broken[0].message
    pinned = _common_problem([papers[0], _paper("BIT 110", ("BIT1", 50), pinned=4)])
    result = solve(pinned, time_limit_s=10, workers=2)
    assert result.failure and result.failure["reasons"][0]["rule"] == "H-E8"


def test_the_common_units_day_is_off_without_common_units_or_a_second_day_or_by_weight():
    from app.exam_solver.model import ExamWeights

    plain = _common_problem([_paper(f"P{i}", (f"BIT{1 + i % 2}", 50)) for i in range(4)])
    assert plain.common_day is None
    common = [_paper("COMS 101", ("BIT1", 50), ("BSC1", 50)), _paper("BIT 110", ("BIT1", 50))]
    assert _common_problem(common, days=1).common_day is None
    off = _common_problem(common)
    off.weights = ExamWeights(common_day=0)
    assert off.common_day is None and check(off, {"COMS 101": 0, "BIT 110": 3}) == []


def test_when_the_second_day_is_full_the_biggest_common_units_keep_it():
    # 800 seats a session: three 700-student papers fill day 2; three 150-student ones would fit only beside two.
    big = [_paper(f"BIG{i}", (f"A{i}", 350), (f"B{i}", 350)) for i in range(3)]
    small = [_paper(f"SMALL{i}", (f"C{i}", 75), (f"D{i}", 75)) for i in range(3)]
    programmes = {f"{k}{i}": k for k in "ABCD" for i in range(3)}
    problem = ExamProblem(
        papers=big + small,
        days=DAYS[:3],
        sessions=3,
        rooms=[_room("A", 400), _room("B", 400)],
        row_programmes=programmes,
    )
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert {pid for pid, t in result.slots.items() if problem.day_of(t) == 1} == {"BIG0", "BIG1", "BIG2"}
    assert result.soft_scores["common_elsewhere"] == 3
