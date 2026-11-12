from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date, timedelta

from app.exam_solver import precheck, sessions
from app.exam_solver import rooms as seating
from app.exam_solver.model import (
    CERTIFICATE,
    COMMON,
    COMMON_STUDENTS,
    DIPLOMA,
    POSTGRADUATE,
    REGULAR,
    ExamProblem,
    ExamRoom,
    ExamWeights,
    Paper,
    Seat,
    Sitting,
    paper_kind,
    venue_group,
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


def test_a_papers_kind_comes_from_its_codes():
    assert paper_kind(["MBAD 845"]) == POSTGRADUATE
    assert paper_kind(["PGDE 721"]) == POSTGRADUATE
    assert paper_kind(["MIT 810"]) == POSTGRADUATE
    assert paper_kind(["MBAD805", "NIHM831"]) == POSTGRADUATE
    assert paper_kind(["COSC 231"]) == ""
    assert paper_kind(["COSC 00107"]) == ""  # a certificate's five figures, not a 7xx
    assert paper_kind(["DIIT 0712"]) == ""
    assert paper_kind(["COSC 231"], REGULAR) == REGULAR  # the Director's choice wins
    assert paper_kind(["MBAD 845"], COMMON) == COMMON


def test_health_and_nursing_papers_are_ordinary_papers():
    assert paper_kind(["NURS 101"]) == ""
    assert paper_kind(["HPA 3111"]) == ""
    assert paper_kind(["NURS 801"]) == POSTGRADUATE  # a postgraduate unit like any other
    assert paper_kind(["NURS 101"], "health") == ""  # a choice made before the rule was revoked
    assert venue_group("", ("NURS 0112",)) == DIPLOMA
    nursing = replace(_paper("NURS 101", ("N1", 50)), codes=("NURS 101",))
    other = _paper("BIT 110", ("BIT1", 40))
    problem = ExamProblem(papers=[nursing, other], days=DAYS[:1], sessions=3, rooms=[_room("A", 100)])
    assert problem.allowed_slots(nursing) == [0, 1, 2]  # midday too
    assert {s.room_id for s in seating.seat_session([nursing, other], problem.rooms)} == {"A"}  # and any room


def test_common_and_postgraduate_papers_sit_first_or_last_on_any_day():
    papers = [_paper(f"C{i}", ("BIT1", 50), ("BSC1", 50)) for i in range(4)]
    papers += [replace(_paper(f"M{i}", (f"M{i}", 10)), kind=POSTGRADUATE) for i in range(3)]
    papers += [_paper(f"R{i}", ("BED1", 30)) for i in range(2)]
    problem = _common_problem(papers)
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert check(problem, result.slots, result.seats) == []
    for p in papers[:7]:
        assert problem.session_of(result.slots[p.id]) in (0, 2), p.id
    assert {problem.day_of(result.slots[f"C{i}"]) for i in range(4)} != {1}  # not one day kept for them
    assert result.soft_scores["common_busiest_day"] == 2  # 4 papers, BIT1 two a day


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


def test_a_venue_the_director_chose_stays_when_the_session_is_re_seated():
    rooms = [_room("A", 100), _room("B", 100)]
    chosen = replace(_paper("P1", ("R1", 90)), fixed_seats=(Seat("P1", "R1", "B", 90),))
    seats = seating.seat_session([chosen, _paper("P2", ("R2", 95))], rooms)
    assert {(s.paper_id, s.room_id) for s in seats} == {("P1", "B"), ("P2", "A")}
    # Numbers changed, or the room closed: seated afresh.
    changed = replace(_paper("P1", ("R1", 70)), fixed_seats=(Seat("P1", "R1", "B", 90),))
    assert sum(s.students for s in seating.seat_session([changed], rooms)) == 70
    closed = replace(_paper("P1", ("R1", 90)), fixed_seats=(Seat("P1", "R1", "GONE", 90),))
    assert {s.room_id for s in seating.seat_session([closed], rooms)} <= {"A", "B"}


def test_a_sessions_postgraduate_papers_share_one_room_undergraduates_elsewhere():
    rooms = [_room("SMALL", 30), _room("MID", 60), _room("BIG", 300)]
    graduates = [replace(_paper(f"M{i}", (f"M{i}", 15)), kind=POSTGRADUATE) for i in range(3)]
    seats = seating.seat_session([_paper("BIT 110", ("BIT1", 20)), *graduates], rooms)
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


def _named(pid: str, staff: str, row: str, kind: str = "") -> Paper:
    return replace(_paper(pid, (row, 10)), invigilator=staff, kind=kind)


def test_one_invigilator_can_cover_a_sessions_postgraduate_papers_in_their_room():
    papers = [_named(f"M{i}", "STF/1", f"M{i}", POSTGRADUATE) for i in range(4)]
    problem = ExamProblem(papers=papers, days=DAYS[:1], sessions=3, rooms=[_room("A", 100)])
    assert precheck.run(problem) == []
    together = {p.id: 0 for p in papers}
    assert [v.rule for v in check(problem, together)] == []  # no seating known yet: taken to share
    seats = seating.seat_session(papers, problem.rooms)
    assert check(problem, together, seats) == []
    result = solve(problem, time_limit_s=10, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure


def test_their_other_papers_still_go_in_another_session_or_room():
    papers = [
        _named("M0", "STF/1", "M0", POSTGRADUATE),
        _named("M1", "STF/1", "M1", POSTGRADUATE),
        _named("R", "STF/1", "R"),
    ]
    problem = ExamProblem(papers=papers, days=DAYS[:1], sessions=3, rooms=[_room("A", 100), _room("B", 100)])
    result = solve(problem, time_limit_s=10, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert result.slots["R"] not in (result.slots["M0"], result.slots["M1"])
    # Same person, same session: fine in one room, a clash in two.
    two = [_named("P0", "STF/2", "R0"), _named("P1", "STF/2", "R1")]
    same = ExamProblem(papers=two, days=DAYS[:1], sessions=3, rooms=[_room("A", 100), _room("B", 100)])
    both = {"P0": 0, "P1": 0}
    assert check(same, both, [Seat("P0", "R0", "A", 10), Seat("P1", "R1", "A", 10)]) == []
    apart = check(same, both, [Seat("P0", "R0", "A", 10), Seat("P1", "R1", "B", 10)])
    assert [v.rule for v in apart] == ["H-E7"]


def _weeks(papers: list[Paper], rooms: list[ExamRoom] | None = None) -> ExamProblem:
    """Mon-Fri for three weeks, starting on a Monday."""
    days = [date(2026, 11, 23) + timedelta(days=w * 7 + d) for w in range(3) for d in range(5)]
    return ExamProblem(papers=papers, days=days, sessions=3, rooms=rooms or [_room("A", 400)])


def test_postgraduate_papers_sit_first_or_last_in_the_first_week_only():
    graduates = [replace(_paper(f"M{i}", (f"M{i}", 10)), kind=POSTGRADUATE) for i in range(12)]
    others = [_paper(f"R{i}", (f"R{i}", 350)) for i in range(40)]
    problem = _weeks(graduates + others)
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert check(problem, result.slots, result.seats) == []
    for p in graduates:
        assert problem.day_of(result.slots[p.id]) < 5 and problem.session_of(result.slots[p.id]) in (0, 2), p.id
    assert any(problem.day_of(result.slots[p.id]) >= 5 for p in others)  # undergraduates carry on after it


def _first_week(start: date, days: int = 14) -> list[date]:
    """The exam days, weekends included, that count as the first week from this start."""
    period = [start + timedelta(days=i) for i in range(days)]
    problem = ExamProblem(papers=[], days=period, sessions=3, rooms=[_room("A", 100)])
    return [d for i, d in enumerate(period) if problem.in_first_week(i * 3)]


def test_the_first_week_ends_on_the_friday_of_the_week_exams_start():
    monday = date(2026, 11, 23)
    friday = date(2026, 11, 27)
    assert _first_week(monday)[-1] == friday and len(_first_week(monday)) == 5
    tuesday = monday + timedelta(days=1)
    assert _first_week(tuesday) == [tuesday + timedelta(days=i) for i in range(4)]  # Tuesday to Friday, not next Monday
    assert _first_week(friday) == [friday]
    for weekend in (date(2026, 11, 28), date(2026, 11, 29)):  # a weekend start has no Friday left: the next one
        assert _first_week(weekend)[-1] == date(2026, 12, 4)


def test_a_tuesday_start_gets_postgraduate_papers_done_by_friday():
    days = [date(2026, 11, 24) + timedelta(days=i) for i in (0, 1, 2, 3, 6, 7, 8, 9, 10)]  # Tue-Fri, then a full week
    graduates = [replace(_paper(f"M{i}", (f"M{i}", 10)), kind=POSTGRADUATE) for i in range(8)]
    problem = ExamProblem(papers=graduates, days=days, sessions=3, rooms=[_room("A", 400)])
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert {problem.days[problem.day_of(t)] for t in result.slots.values()} <= set(days[:4])
    next_monday = 4 * 3
    assert [v.rule for v in check(problem, {**result.slots, "M0": next_monday})] == ["H-E10"]
    too_many = [replace(_paper(f"M{i}", ("MBA1", 10)), kind=POSTGRADUATE) for i in range(9)]
    short = ExamProblem(papers=too_many, days=days, sessions=3, rooms=[_room("A", 400)])
    assert "room for 8" in precheck.run(short)[0]["message"]  # 4 days, 2 a day


def test_a_postgraduate_paper_moved_or_pinned_after_the_first_week_breaks_the_rule():
    graduate = replace(_paper("MBAD 845", ("M1", 10)), kind=POSTGRADUATE)
    problem = _weeks([graduate])
    assert check(problem, {"MBAD 845": 12}) == []  # Friday's last session
    broken = check(problem, {"MBAD 845": 15})  # next Monday's first
    assert [v.rule for v in broken] == ["H-E10"] and "first week" in broken[0].message
    result = solve(_weeks([replace(graduate, pinned=15)]), time_limit_s=10, workers=2)
    assert result.failure and result.failure["reasons"][0]["rule"] == "H-E10"


def test_a_class_with_more_postgraduate_papers_than_the_first_week_holds_is_named():
    papers = [replace(_paper(f"M{i}", ("MBA1", 10)), kind=POSTGRADUATE) for i in range(11)]
    problem = _weeks(papers)
    problem.row_labels = {"MBA1": "MBA Y1S1"}
    findings = precheck.run(problem)
    assert [f["rule"] for f in findings] == ["H-E10"]
    assert "MBA Y1S1 sits 11 postgraduate papers" in findings[0]["message"] and "room for 10" in findings[0]["message"]
    assert precheck.run(_weeks(papers[:10])) == []


def test_postgraduate_students_who_cant_fit_the_first_week_are_reported():
    papers = [replace(_paper(f"M{i}", (f"M{i}", 90)), kind=POSTGRADUATE) for i in range(12)]
    findings = precheck.run(_weeks(papers, rooms=[_room("A", 100)]))
    assert [f["entity"] for f in findings] == ["first week"]


def test_the_first_week_rule_is_off_for_a_draft_made_before_it():
    graduate = replace(_paper("MBAD 845", ("M1", 10)), kind=POSTGRADUATE)
    problem = _weeks([graduate])
    problem.weights = ExamWeights.from_dict({"postgraduate_first_week": 0, "category_rules": 1})
    assert check(problem, {"MBAD 845": 15}) == []
    assert ExamWeights.from_dict(None).postgraduate_first_week == 1


def test_students_a_room_cant_hold_stay_in_its_building():
    # 60 don't fit what is left of UTC 1. ADM 1 has the seats, but they stay in UTC.
    rooms = [_room("UTC 1", 100, "UTC"), _room("UTC 2", 50, "UTC"), _room("UTC 3", 20, "UTC")]
    rooms.append(_room("ADM 1", 60, "ADM"))
    placed = seating.seat_session([_paper("P", ("R1", 90), ("R2", 60))], rooms)
    assert {s.room_id for s in placed} <= {"UTC 1", "UTC 2", "UTC 3"}
    assert sum(s.students for s in placed) == 150


def test_a_class_row_bigger_than_every_room_stays_in_one_building():
    rooms = [_room("UTC 1", 100, "UTC"), _room("UTC 2", 40, "UTC"), _room("UTC 3", 40, "UTC")]
    rooms.append(_room("ADM 1", 50, "ADM"))
    placed = seating.seat_session([_paper("P", ("HUGE", 150))], rooms)
    assert {s.room_id for s in placed} <= {"UTC 1", "UTC 2", "UTC 3"}
    assert sum(s.students for s in placed) == 150


def test_a_paper_starts_in_the_building_that_holds_all_of_it():
    # 90 fit ADM 1 most tightly, but the other 60 wouldn't: the whole paper goes to UTC.
    rooms = [_room("ADM 1", 95, "ADM"), _room("UTC 1", 100, "UTC"), _room("UTC 2", 100, "UTC")]
    placed = seating.seat_session([_paper("P", ("R1", 90), ("R2", 60))], rooms)
    assert {s.room_id for s in placed} == {"UTC 1", "UTC 2"}


def test_a_small_paper_is_not_scattered_over_a_buildings_leftover_seats():
    rooms = [_room("A 1", 100, "A"), _room("A 2", 15, "A"), _room("B 1", 100, "B")]
    papers = [_paper("BIG", ("R1", 90)), _paper("SMALL", ("R2", 20))]
    placed = seating.seat_session(papers, rooms)
    assert len({s.room_id for s in placed if s.paper_id == "SMALL"}) == 1


def test_a_paper_too_big_for_any_building_uses_as_few_as_it_can():
    rooms = [_room("A 1", 50, "A"), _room("B 1", 100, "B"), _room("B 2", 100, "B"), _room("C 1", 60, "C")]
    placed = seating.seat_session([_paper("P", ("R1", 100), ("R2", 100), ("R3", 40))], rooms)
    assert {"B 1", "B 2"} <= {s.room_id for s in placed}  # B has the most seats
    assert len({s.room_id[0] for s in placed}) == 2  # and one more building takes the rest
    assert sum(s.students for s in placed) == 240


def test_seating_never_overfills_a_room_and_seats_everyone():
    import random

    rng = random.Random(7)  # noqa: S311
    seated = 0
    for _ in range(3000):
        rooms = [
            _room(f"{b} {i}", rng.choice((20, 40, 60, 90, 100, 150, 270)), b)
            for b in rng.sample("ABCDE", rng.randint(1, 5))
            for i in range(rng.randint(1, 4))
        ]
        papers = [
            _paper(f"P{i}", *[(f"R{i}-{j}", rng.randint(0, 120)) for j in range(rng.randint(1, 3))])
            for i in range(rng.randint(1, 5))
        ]
        try:
            placed = seating.seat_session(papers, rooms)
        except seating.SeatingError:
            continue
        seated += 1
        used: dict[str, int] = defaultdict(int)
        for s in placed:
            used[s.room_id] += s.students
        by_id = {r.id: r for r in rooms}
        assert all(n <= by_id[room].seats for room, n in used.items())
        for p in papers:
            assert sum(s.students for s in placed if s.paper_id == p.id) == p.students
    assert seated > 500


def _level_paper(code: str, students: int) -> Paper:
    return replace(_paper(code, (code, students)), codes=(code,))


def test_a_codes_leading_zeros_say_its_level():
    assert venue_group("", ("COSC 00101",)) == CERTIFICATE
    assert venue_group("", ("CPLM 00131",)) == CERTIFICATE
    assert venue_group("", ("COSC 00102", "CIBM 00161")) == CERTIFICATE
    assert venue_group("", ("DIBM 0112",)) == DIPLOMA
    assert venue_group("", ("COSC 0172", "COSC 0170")) == DIPLOMA
    assert venue_group("common", ("DIBM 0112",)) == DIPLOMA
    assert venue_group("", ("COSC 231",)) is None
    assert venue_group("", ("COSC 0172", "COSC 231")) is None  # sat by a degree class too
    assert venue_group("", ()) is None
    assert venue_group(POSTGRADUATE, ("MBAD 845",)) == POSTGRADUATE


def test_a_sessions_certificate_and_diploma_papers_each_share_their_own_room():
    rooms = [_room("A", 30), _room("B", 60), _room("C", 100), _room("D", 300)]
    papers = [
        _level_paper("COSC 00101", 15),
        _level_paper("CIBM 00112", 10),
        _level_paper("DIBM 0112", 40),
        _level_paper("DJMC 0123", 30),
        _level_paper("COSC 231", 20),
    ]
    seats = {s.paper_id: s.room_id for s in seating.seat_session(papers, rooms)}
    assert seats["COSC 00101"] == seats["CIBM 00112"] == "A"  # the smallest that holds the 25
    assert seats["DIBM 0112"] == seats["DJMC 0123"] == "C"  # the smallest left that holds the 70
    assert seats["COSC 231"] not in {"A", "C"}


def test_a_level_too_big_for_one_room_stays_in_one_building():
    rooms = [_room("UTC 1", 60, "UTC"), _room("UTC 2", 60, "UTC"), _room("ADM 1", 60, "ADM")]
    papers = [_level_paper(f"DIBM 011{i}", 40) for i in range(3)]
    seats = seating.seat_session(papers, rooms)
    assert {s.room_id for s in seats} == {"UTC 1", "UTC 2"}


def test_others_may_use_a_levels_room_when_nothing_else_is_left():
    papers = [_level_paper("DIBM 0112", 20), _level_paper("COSC 231", 50)]
    seats = {s.paper_id: s.room_id for s in seating.seat_session(papers, [_room("A", 100)])}
    assert seats == {"DIBM 0112": "A", "COSC 231": "A"}


def test_a_diploma_paper_keeps_its_session_rules_and_stays_common():
    # Sat by two programmes: still a common paper, so first or last session. One programme: any session.
    problem = _common_problem([_level_paper("DIBM 0112", 10)], days=1)
    alone = problem.papers[0]
    assert problem.category(alone) == REGULAR and problem.allowed_slots(alone) == [0, 1, 2]
    assert not problem.first_week_only(alone)
    assert paper_kind(["DIBM 0112"], []) == ""
    joint = replace(_level_paper("DIBM 0113", 10), rows=(Sitting("D1", 5), Sitting("D2", 5)), codes=("DIBM 0113",))
    both = replace(problem, papers=[joint], row_programmes={"D1": "DIBM", "D2": "DHRM"})
    assert both.category(joint) == COMMON and both.allowed_slots(joint) == [0, 2]


def _big(pid: str, students: int) -> Paper:
    return _paper(pid, (f"{pid}-1", students))


def test_a_paper_of_more_than_3000_students_counts_as_common():
    assert COMMON_STUDENTS == 3000
    problem = _common_problem([], rooms=[_room("A", 5000)])
    at_limit, over = _big("AT", 3000), _big("OVER", 3001)
    assert problem.category(at_limit) == REGULAR
    assert problem.category(over) == COMMON and problem.common_by_numbers(over)
    # The Director's choice, or its own category, comes first.
    assert problem.category(replace(over, kind=REGULAR)) == REGULAR
    assert problem.category(replace(over, kind=POSTGRADUATE)) == POSTGRADUATE
    assert not problem.common_by_numbers(replace(over, kind=COMMON))


def test_the_first_or_last_session_is_a_preference_for_a_paper_common_by_its_numbers():
    big = _big("BIG", 3500)
    problem = _common_problem([big], days=1, rooms=[_room("A", 5000)])
    assert problem.allowed_slots(big) == [0, 1, 2]  # no session is closed to it
    assert not problem.edges_only(big)
    assert check(problem, {"BIG": 1}, [Seat("BIG", "BIG-1", "A", 3500)]) == []  # midday breaks no hard rule
    assert soft_scores(problem, {"BIG": 1}, [Seat("BIG", "BIG-1", "A", 3500)])["common_by_numbers_midday"] == 1
    assert soft_scores(problem, {"BIG": 0}, [Seat("BIG", "BIG-1", "A", 3500)])["common_by_numbers_midday"] == 0


def test_the_solver_seats_papers_common_by_numbers_first_or_last_when_it_can():
    # Day two's midday is otherwise the cheapest place for nobody; these two should still take the edges.
    papers = [_big("BIG1", 3500), _big("BIG2", 3400), _paper("R", ("BIG1-1", 10))]
    problem = _common_problem(papers, days=2, rooms=[_room("A", 5000)])
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert problem.is_edge(result.slots["BIG1"]) and problem.is_edge(result.slots["BIG2"])
    assert result.soft_scores["common_by_numbers_midday"] == 0


def test_a_paper_common_by_its_numbers_goes_midday_when_it_must():
    # Three big papers and one exam day: both edges fill up, and that must not make it impossible.
    papers = [_big(f"BIG{i}", 3100) for i in range(3)]
    problem = _common_problem(papers, days=1, rooms=[_room("A", 3200)])
    result = solve(problem, time_limit_s=20, workers=2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.failure
    assert result.soft_scores["common_by_numbers_midday"] == 1
