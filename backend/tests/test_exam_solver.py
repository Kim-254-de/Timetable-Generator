from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date, timedelta

from app.exam_solver import precheck, sessions
from app.exam_solver import rooms as seating
from app.exam_solver.model import (
    COMMON,
    HEALTH,
    POSTGRADUATE,
    REGULAR,
    ExamProblem,
    ExamRoom,
    ExamWeights,
    Paper,
    Sitting,
    paper_kind,
)
from app.exam_solver.solve import soft_scores, solve
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


def _common_problem(papers: list[Paper], days: int = 3, rooms: list[ExamRoom] | None = None) -> ExamProblem:
    programmes = {"BIT1": "BIT", "BIT2": "BIT", "BSC1": "BSC", "BED1": "BED", "BCOM1": "BCOM"}
    return ExamProblem(
        papers=papers,
        days=DAYS[:days],
        sessions=3,
        rooms=rooms or [_room("A", 400), _room("B", 400)],
        row_programmes=programmes,
    )


def test_a_papers_kind_comes_from_its_codes_and_health_wins():
    health = ["NURS", "hpa"]
    assert paper_kind(["MBAD 845"], health) == POSTGRADUATE
    assert paper_kind(["PGDE 721"], health) == POSTGRADUATE
    assert paper_kind(["MIT 810"], health) == POSTGRADUATE
    assert paper_kind(["MBAD805", "NIHM831"], health) == POSTGRADUATE
    assert paper_kind(["COSC 231"], health) == ""
    assert paper_kind(["COSC 00107"], health) == ""  # a certificate's five figures, not a 7xx
    assert paper_kind(["DIIT 0712"], health) == ""
    assert paper_kind(["HPA 3111"], health) == HEALTH
    assert paper_kind(["NURS 801"], health) == HEALTH  # postgraduate nursing: health wins
    assert paper_kind(["COSC 231"], health, REGULAR) == REGULAR  # the Director's choice wins
    assert paper_kind(["MBAD 845"], health, COMMON) == COMMON


def test_common_postgraduate_and_health_papers_sit_first_or_last_on_any_day():
    papers = [_paper(f"C{i}", ("BIT1", 50), ("BSC1", 50)) for i in range(4)]
    papers += [replace(_paper(f"M{i}", (f"M{i}", 10)), kind=POSTGRADUATE) for i in range(3)]
    papers += [replace(_paper(f"N{i}", (f"N{i}", 20)), kind=HEALTH) for i in range(3)]
    papers += [_paper(f"R{i}", (f"BED1", 30)) for i in range(2)]
    problem = _common_problem(papers, rooms=[_room("A", 400), _room("H", 100), _room("B", 400)])
    problem.rooms[1] = ExamRoom(id="H", code="H", block="H", seats=100, health=True)
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert check(problem, result.slots, result.seats) == []
    for p in papers[:10]:
        assert problem.session_of(result.slots[p.id]) in (0, 2), p.id
    assert {problem.day_of(result.slots[f"C{i}"]) for i in range(4)} != {1}  # not one day kept for them
    assert result.soft_scores["common_busiest_day"] == 2  # 4 papers, BIT1 two a day
    assert {s.room_id for s in result.seats if s.paper_id.startswith("N")} == {"H"}


def test_a_class_can_sit_morning_and_evening_on_one_day_when_it_must():
    papers = [_paper(f"C{i}", ("BIT1", 50), ("BSC1", 50)) for i in range(4)]
    problem = _common_problem(papers, days=2)
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert sorted(result.slots.values()) == [0, 2, 3, 5]
    assert result.soft_scores["back_to_back"] == 0


def test_moving_or_pinning_a_common_paper_to_midday_breaks_the_rule():
    papers = [_paper("COMS 101", ("BIT1", 50), ("BSC1", 50)), _paper("BIT 110", ("BIT1", 50))]
    problem = _common_problem(papers)
    assert check(problem, {"COMS 101": 3, "BIT 110": 4}) == []  # a regular paper can sit midday
    broken = check(problem, {"COMS 101": 1, "BIT 110": 4})
    assert [v.rule for v in broken] == ["H-E8"] and "first or last session" in broken[0].message
    pinned = _common_problem([_paper("COMS 101", ("BIT1", 50), ("BSC1", 50), pinned=4)])
    result = solve(pinned, time_limit_s=10, workers=2)
    assert result.failure and result.failure["reasons"][0]["rule"] == "H-E8"


def test_the_rules_are_off_for_a_run_made_before_them():
    papers = [_paper("COMS 101", ("BIT1", 50), ("BSC1", 50))]
    off = _common_problem(papers)
    off.weights = ExamWeights.from_dict({"category_rules": 0, "common_day": 5000})  # an old run's weights
    assert check(off, {"COMS 101": 1}) == []
    assert not off.edges_only(papers[0])


def test_health_papers_sit_in_the_health_unit_and_others_keep_out_while_they_can():
    rooms = [ExamRoom(id="H", code="H", block="H", seats=60, health=True), _room("A", 200)]
    nursing = replace(_paper("NURS 101", ("N1", 50)), kind=HEALTH)
    other = _paper("BIT 110", ("BIT1", 100))
    small = _paper("BIT 111", ("BIT2", 10))
    seats = seating.seat_session([small, nursing, other], rooms)
    assert {s.room_id for s in seats if s.paper_id == "NURS 101"} == {"H"}
    assert {s.room_id for s in seats if s.paper_id != "NURS 101"} == {"A"}
    # Others can use a health room when nothing else is left.
    full = seating.seat_session([_paper("BIG", ("R1", 200)), _paper("MORE", ("R2", 40))], rooms)
    assert {s.room_id for s in full if s.paper_id == "MORE"} == {"H"}


def test_the_precheck_says_when_the_health_unit_cant_hold_its_papers():
    nursing = replace(_paper("NURS 101", ("N1", 50)), kind=HEALTH)
    none = _common_problem([nursing])
    assert [(f["rule"], f["entity"]) for f in precheck.run(none)] == [("H-E9", "health unit")]
    small = _common_problem([nursing], rooms=[ExamRoom(id="H", code="H", block="H", seats=40, health=True), _room("A", 100)])
    assert [(f["rule"], f["entity"]) for f in precheck.run(small)] == [("H-E9", "NURS 101")]
    # A paper with no number yet doesn't need the room yet.
    assert precheck.run(_common_problem([replace(_paper("NURS 102", ("N1", 0)), kind=HEALTH)])) == []


def test_the_solver_keeps_a_sessions_health_students_within_the_health_unit():
    papers = [replace(_paper(f"N{i}", (f"N{i}", 40)), kind=HEALTH) for i in range(4)]
    rooms = [ExamRoom(id="H", code="H", block="H", seats=50, health=True), _room("A", 500)]
    problem = _common_problem(papers, days=2, rooms=rooms)
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert len(set(result.slots.values())) == 4  # one at a time: the unit seats 50
    assert check(problem, result.slots, result.seats) == []


def test_a_sessions_postgraduate_papers_share_one_room_undergraduates_elsewhere():
    rooms = [_room("SMALL", 30), _room("MID", 60), _room("BIG", 300)]
    graduates = [replace(_paper(f"M{i}", (f"M{i}", 15)), kind=POSTGRADUATE) for i in range(3)]
    seats = seating.seat_session([_paper("BIT 110", ("BIT1", 20))] + graduates, rooms)
    assert {s.room_id for s in seats if s.paper_id.startswith("M")} == {"MID"}  # the smallest that holds all 45
    assert {s.room_id for s in seats if s.paper_id == "BIT 110"} != {"MID"}


def test_postgraduate_papers_too_big_for_one_room_take_few_and_the_score_says_so():
    rooms = [_room("A", 30), _room("B", 30), _room("C", 30, "OTHER")]
    graduates = [replace(_paper(f"M{i}", (f"M{i}", 20)), kind=POSTGRADUATE) for i in range(2)]
    problem = ExamProblem(papers=graduates, days=DAYS[:1], sessions=3, rooms=rooms)
    seats = seating.seat_session(graduates, rooms)
    assert len({s.room_id for s in seats}) == 2 and {s.room_id for s in seats} == {"A", "B"}
    assert soft_scores(problem, {"M0": 0, "M1": 0}, seats)["postgraduate_extra_rooms"] == 1
def _guessed(pid: str, code: str, row: str = "COSC Y1S1", students: int = 10) -> Paper:
    return Paper(id=pid, label=pid, rows=(Sitting(row, students, guessed=True),), codes=(code,))


def test_a_guessed_class_never_makes_the_timetable_impossible():
    # Six papers one guessed class "sits" over one day: as a known class that breaks H-E2.
    papers = [_guessed(f"P{i}", f"COSC 10{i}") for i in range(6)]
    problem = ExamProblem(papers=papers, days=DAYS[:1], sessions=3, rooms=[_room("A", 100)])
    assert precheck.run(problem) == []
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert check(problem, result.slots, result.seats) == []


def test_a_guessed_class_still_takes_seats_and_is_kept_apart_softly():
    papers = [_guessed(f"P{i}", f"COSC 10{i}", students=30 + i) for i in range(3)]
    problem = ExamProblem(papers=papers, days=DAYS[:3], sessions=3, rooms=[_room("A", 100)])
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert {s.paper_id: s.students for s in result.seats} == {"P0": 30, "P1": 31, "P2": 32}
    assert len(set(result.slots.values())) == 3  # S-E4
    assert result.soft_scores["guessed_clashes"] == 0


def test_seats_still_limit_guessed_papers():
    papers = [_guessed("P0", "COSC 100", students=120)]
    problem = ExamProblem(papers=papers, days=DAYS[:1], sessions=3, rooms=[_room("A", 100)])
    assert [f["rule"] for f in precheck.run(problem)] == ["H-E3"]


def test_a_known_class_stays_hard_beside_a_guessed_one():
    # R1 is known on all three papers, so two a day holds; the guess adds nothing to it.
    papers = [
        Paper(
            id=f"P{i}",
            label=f"P{i}",
            rows=(Sitting("R1", 20), Sitting("GUESS", 5, guessed=True)),
            codes=(f"COSC 10{i}",),
        )
        for i in range(3)
    ]
    problem = ExamProblem(papers=papers, days=DAYS[:2], sessions=3, rooms=[_room("A", 100)])
    assert sorted(problem.rows()) == ["R1"]
    result = solve(problem, time_limit_s=20, workers=2)
    per_day = defaultdict(int)
    for t in result.slots.values():
        per_day[problem.day_of(t)] += 1
    assert max(per_day.values()) == 2


def test_a_joint_paper_with_a_guessed_class_is_common_by_its_codes():
    joint = Paper(id="J", label="J", rows=(Sitting("BITE Y1S1", 40, guessed=True),), codes=("BITE 110", "COSC 110"))
    single = _guessed("S", "BITE 111", row="BITE Y1S1")
    problem = ExamProblem(
        papers=[joint, single], days=DAYS[:3], sessions=3, rooms=[_room("A", 100)], row_programmes={"BITE Y1S1": "BITE"}
    )
    assert problem.is_common(joint) and not problem.is_common(single)


def test_a_class_with_no_number_yet_is_held_apart_and_needs_no_seat():
    """A class the master timetable names, before anyone syncs: every hard rule, nothing to seat."""
    papers = [_paper(f"P{i}", ("BCOM Y2S1", 0)) for i in range(4)] + [_paper("BIG", ("BCOM Y2S1", 0), ("BIT Y1S1", 90))]
    problem = ExamProblem(papers=papers, days=DAYS[:3], sessions=3, rooms=[_room("A", 100)])
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert check(problem, result.slots, result.seats) == []
    assert len(set(result.slots.values())) == 5  # one class: never two papers in a session
    per_day = defaultdict(int)
    for t in result.slots.values():
        per_day[problem.day_of(t)] += 1
    assert max(per_day.values()) <= 2
    assert [(s.paper_id, s.row_id, s.students) for s in result.seats] == [("BIG", "BIT Y1S1", 90)]


def test_the_precheck_counts_classes_with_no_number_yet():
    papers = [_paper(f"P{i}", ("BCOM Y2S1", 0)) for i in range(5)]
    problem = ExamProblem(papers=papers, days=DAYS[:2], sessions=3, rooms=[_room("A", 100)])
    assert [f["rule"] for f in precheck.run(problem)] == ["H-E2"]


def test_papers_of_different_classes_with_no_numbers_are_spread():
    papers = [_paper(f"P{i}", (f"R{i}", 0)) for i in range(12)]
    problem = ExamProblem(papers=papers, days=DAYS[:2], sessions=3, rooms=[_room("A", 100)])
    result = solve(problem, time_limit_s=20, workers=2)
    per_slot = defaultdict(int)
    for t in result.slots.values():
        per_slot[t] += 1
    assert max(per_slot.values()) == 2  # 12 papers over 6 sessions, though nothing has to be seated
