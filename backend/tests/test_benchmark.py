"""
The Sep-Dec 2026 benchmark (tools/benchmark.py) on the hand-made timetable
extracted from the Directorate's PDF. The quick tests check the fixture and
the scoring; the full-university solve is opt-in: pytest -m benchmark.
"""

from __future__ import annotations

import json

import pytest

from app.solver import cpsat
from tools.benchmark import FIXTURE, build, summarise


@pytest.fixture(scope="module")
def benchmark():
    return build(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_fixture_matches_the_printed_timetable(benchmark):
    problem, handmade = benchmark
    assert len(problem.class_rows) == 405
    assert len(problem.sessions) == 1663
    assert len(problem.rooms) == 102
    assert set(handmade) == {s.key for s in problem.sessions}


def test_handmade_timetable_scores(benchmark):
    problem, handmade = benchmark
    report = summarise(problem, handmade)
    assert report["hard_violations"] == {}
    assert report["soft"]["early_starts"] == 411
    assert report["soft"]["gaps"] == 55


@pytest.mark.benchmark
def test_solver_beats_the_handmade_timetable(benchmark):
    problem, handmade = benchmark
    baseline = summarise(problem, handmade)["soft"]
    result = cpsat.solve(problem, time_limit_s=570, workers=8)
    assert result.placements, result.failure
    assert result.solve_seconds < 600
    report = summarise(problem, result.placements)
    assert report["hard_violations"] == {}
    for measure in ("gaps", "early_starts", "late_starts"):
        assert report["soft"][measure] < baseline[measure], measure
