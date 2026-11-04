"""
Hosting with no Redis or worker (a single web service): runs are solved in a
background thread of the web process, and a run cut off by a restart is
marked failed rather than left waiting.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Run, RunStatus
from app.services import runs
from tests.conftest import sign_in
from tests.test_api import setup_term
from tests.test_exams import setup_exams


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.fixture
def no_queue() -> Iterator[None]:
    """Not inline, and Redis on a port nothing listens on."""
    saved = {k: os.environ.get(k) for k in ("RUN_INLINE", "REDIS_URL")}
    os.environ["RUN_INLINE"] = "false"
    os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
    get_settings.cache_clear()
    yield
    runs.drain_local_runs()
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    get_settings.cache_clear()


def test_a_teaching_run_is_solved_in_the_web_process_when_redis_is_unreachable(client, smarttt, no_queue):
    sign_in(client)
    term_id = setup_term(client)
    run = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))
    assert run["status"] == "queued"  # answered at once; no 500
    runs.drain_local_runs()
    done = ok(client.get(f"/api/runs/{run['id']}"))
    assert done["status"] == "succeeded", done["failure"]
    assert ok(client.get(f"/api/drafts/{done['draft_id']}?view=row"))["draft"]["violation_count"] == 0


def test_an_exam_run_too_and_with_no_redis_set_at_all(client, smarttt, teaching, no_queue):
    os.environ["REDIS_URL"] = ""
    get_settings.cache_clear()
    sign_in(client)
    term_id = setup_exams(client, teaching)
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    run = ok(client.post("/api/exam-runs", json={"term_id": term_id, "time_limit_s": 20}))
    runs.drain_local_runs()
    done = ok(client.get(f"/api/runs/{run['id']}"))
    assert done["status"] == "succeeded", done["failure"]


def test_a_run_cut_off_by_a_restart_is_marked_failed(client, smarttt, db: Session, no_queue):
    sign_in(client)
    term_id = setup_term(client)
    run = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))
    runs.drain_local_runs()
    stuck = db.get(Run, uuid.UUID(run["id"]))
    assert stuck is not None
    stuck.status = RunStatus.RUNNING  # as if the process died mid-solve
    db.commit()

    assert runs.fail_interrupted_runs() == 1
    after = ok(client.get(f"/api/runs/{run['id']}"))
    assert after["status"] == "failed"
    assert after["failure"]["reasons"][0]["message"] == runs.INTERRUPTED
