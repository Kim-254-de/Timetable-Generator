"""An approved version stays as approved, can reach SMARTTT later, and dead solver runs don't hang."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.models import Run, RunStatus, utcnow
from tests.conftest import sign_in
from tests.test_api import ok, setup_term


def _cells(client, draft_id):
    grid = ok(client.get(f"/api/drafts/{draft_id}?view=row"))
    return grid, sorted(
        (c["key"], c["unit_code"], c["group"], c["day"], c["room"]) for e in grid["entities"] for c in e["cells"]
    )


def test_an_approved_version_is_kept_as_approved(client, smarttt):
    sign_in(client)
    term_id = setup_term(client)
    draft_id = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))["draft_id"]
    ok(client.post(f"/api/drafts/{draft_id}/publish", json={}))
    grid, before = _cells(client, draft_id)
    assert grid["as_approved"] is True

    # Later edits: a unit renamed and another regrouped.
    offerings = {o["unit_code"]: o for o in ok(client.get(f"/api/terms/{term_id}/offerings"))}
    ok(client.patch(f"/api/offerings/{offerings['COSC 103']['id']}", json={"unit_code": "COSC 113"}))
    smed = offerings["SMED 100"]
    for group in smed["groups"][1:]:
        ok(client.delete(f"/api/groups/{group['id']}"))

    _grid, after = _cells(client, draft_id)
    assert after == before  # the approved version reads (and downloads) as approved
    pdf = client.get(f"/api/drafts/{draft_id}/export.pdf?view=row")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_a_version_smarttt_missed_is_sent_later(client, smarttt):
    sign_in(client)
    term_id = setup_term(client)
    draft_id = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))["draft_id"]

    smarttt.down = True
    published = ok(client.post(f"/api/drafts/{draft_id}/publish", json={}))
    assert published["smarttt"]["sent"] is False
    smarttt.down = False
    version = ok(client.get(f"/api/terms/{term_id}"))["publications"][0]
    assert version["sent_to_smarttt"] is False and version["can_send"] is True

    smarttt.down = True
    still_down = client.post(f"/api/terms/{term_id}/publications/1/send")
    assert still_down.status_code == 503
    smarttt.down = False
    sent = ok(client.post(f"/api/terms/{term_id}/publications/1/send"))
    assert sent["sent_to_smarttt"] is True and sent["can_send"] is False
    assert smarttt.publications[1]["session_count"] == len(smarttt.payloads[-1]["sessions"])
    again = client.post(f"/api/terms/{term_id}/publications/1/send")
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_SENT"


def test_runs_whose_worker_died_are_marked_failed(client, smarttt, db):
    sign_in(client)
    term_id = setup_term(client)
    run = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))
    long_ago = utcnow() - timedelta(hours=3)
    stuck = db.scalar(select(Run).where(Run.id == uuid.UUID(run["id"])))
    stuck.status, stuck.started_at = RunStatus.RUNNING, long_ago
    lost = Run(
        term_id=stuck.term_id,
        snapshot_id=stuck.snapshot_id,
        mode=stuck.mode,
        weights=stuck.weights,
        time_limit_s=20,
        created_by="test",
        progress={"phase": "queued"},
        status=RunStatus.QUEUED,
        created_at=long_ago,
    )
    db.add(lost)
    db.commit()

    listed = {r["id"]: r for r in ok(client.get(f"/api/terms/{term_id}/runs"))}
    assert listed[run["id"]]["status"] == "failed"
    assert listed[str(lost.id)]["status"] == "failed"
    assert "worker" in listed[str(lost.id)]["failure"]["reasons"][0]["message"]


def test_the_allocator_learns_when_smarttt_has_the_version(client, smarttt):
    sign_in(client)
    term_id = setup_term(client)
    headers = {"X-API-Key": "test-allocator-key"}
    draft_id = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))["draft_id"]

    smarttt.down = True
    ok(client.post(f"/api/drafts/{draft_id}/publish", json={}))
    smarttt.down = False
    terms = ok(client.get("/api/integrations/allocator/terms", headers=headers))
    assert terms[0]["published_version"] == 1 and terms[0]["in_smarttt"] is False  # approved while SMARTTT was down
    assert terms[0]["smarttt_term_id"]

    ok(client.post(f"/api/terms/{term_id}/publications/1/send"))
    terms = ok(client.get("/api/integrations/allocator/terms", headers=headers))
    assert terms[0]["in_smarttt"] is True
