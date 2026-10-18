"""
Soft-constraint scores of a finished timetable, computed from the placements
alone (so the hand-made timetable can be scored the same way as a solver
result). Each score counts occurrences, not weighted penalties:

  gaps              S1 one-hour gaps inside a class row's day
  same_day          S2 pairs of a group's sessions on the same day
  long_day          S3 hours beyond 5 in a class row's day
  edge_hours        S4 session-hours at 07:00 or from 17:00
  early_starts      sessions starting at 07:00 (reported for comparison)
  late_starts       sessions starting at 15:00 or later (reported for comparison)
  department_peak   S5 sum over departments of their busiest hour
  building_changes  S6 extra buildings a class row uses in a day
  empty_seats       S7 empty seats across all sessions
  moved             S8 sessions not where they were (repair)
"""

from __future__ import annotations

from collections import defaultdict

from app.solver.model import HOURS_PER_DAY, Placement, Problem, covered, slot_day, slot_hour


def score(problem: Problem, placements: dict[str, Placement]) -> dict[str, float]:
    rooms = problem.rooms_by_id()
    occupied: dict[str, set[int]] = defaultdict(set)
    buildings: dict[tuple[str, int], set[str]] = defaultdict(set)
    group_days: dict[str, list[int]] = defaultdict(list)
    dept_load: dict[tuple[int, int], int] = defaultdict(int)
    result = {
        k: 0.0
        for k in (
            "gaps",
            "same_day",
            "long_day",
            "edge_hours",
            "early_starts",
            "late_starts",
            "department_peak",
            "building_changes",
            "empty_seats",
            "moved",
        )
    }

    for s in problem.sessions:
        p = placements.get(s.key)
        if p is None:
            continue
        hours = list(covered(p.start, s.length))
        for row_id in s.class_row_ids:
            occupied[row_id].update(hours)
            room = rooms.get(p.room_id)
            if room is not None:
                buildings[(row_id, slot_day(p.start))].add(room.building)
        group_days[s.group_id].append(slot_day(p.start))
        for t in hours:
            dept_load[(s.department_id, t)] += 1
            if slot_hour(t) == 7 or slot_hour(t) >= 17:
                result["edge_hours"] += 1
        if slot_hour(p.start) == 7:
            result["early_starts"] += 1
        if slot_hour(p.start) >= 15:
            result["late_starts"] += 1
        room = rooms.get(p.room_id)
        if room is not None:
            result["empty_seats"] += max(0, room.capacity - s.students)
        if s.previous is not None and s.previous != p:
            result["moved"] += 1

    for slots in occupied.values():
        for day in range(5):
            base = day * HOURS_PER_DAY
            day_slots = [base + h in slots for h in range(HOURS_PER_DAY)]
            result["long_day"] += max(0, sum(day_slots) - 5)
            for h in range(1, HOURS_PER_DAY - 1):
                if day_slots[h - 1] and not day_slots[h] and day_slots[h + 1]:
                    result["gaps"] += 1

    for days in group_days.values():
        for i, a in enumerate(days):
            result["same_day"] += sum(1 for b in days[i + 1 :] if a == b)

    peaks: dict[int, int] = defaultdict(int)
    for (dept, _t), load in dept_load.items():
        peaks[dept] = max(peaks[dept], load)
    result["department_peak"] = float(sum(peaks.values()))
    result["building_changes"] = float(sum(max(0, len(b) - 1) for b in buildings.values()))
    return result


def weighted(problem: Problem, scores: dict[str, float]) -> float:
    w = problem.weights
    return (
        w.gaps * scores["gaps"]
        + w.same_day * scores["same_day"]
        + w.long_day * scores["long_day"]
        + w.edge_hours * scores["edge_hours"]
        + w.department_peak * scores["department_peak"]
        + w.building_changes * scores["building_changes"]
        + w.room_fit * scores["empty_seats"] / 10
        + w.keep_previous * scores["moved"]
    )
