"""The Director switches SMARTTT from teaching to exams, and closes the exam period."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from tests.conftest import sign_in
from tests.fake_smarttt import DIRECTOR, TERM, FakeSmarttt
from tests.fake_teaching import FakeTeaching
from tests.test_exams import ok, setup_exams


def _future_week() -> tuple[date, date]:
    """A Monday-Friday exam period five weeks from now."""
    monday = date.today() + timedelta(days=35 - date.today().weekday())
    return monday, monday + timedelta(days=4)


def _smarttt_term(client: TestClient, teaching: FakeTeaching) -> tuple[str, date, date]:
    term_id = setup_exams(client, teaching, smarttt_term_id=TERM["id"])
    first, last = _future_week()
    ok(
        client.patch(
            f"/api/terms/{term_id}/exam-period",
            json={"exam_start": first.isoformat(), "exam_end": last.isoformat(), "exam_days_off": []},
        )
    )
    return term_id, first, last


def _publish_exams(client: TestClient, teaching: FakeTeaching, term_id: str, expect_ok: bool = True) -> None:
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    draft_id = ok(client.post("/api/exam-runs", json={"term_id": term_id, "time_limit_s": 20}))["draft_id"]
    ok(client.post(f"/api/exam-drafts/{draft_id}/share"))
    shared = ok(
        client.get(
            f"/api/integrations/attendance/terms/{term_id}/exam-draft", headers={"X-API-Key": "test-attendance-key"}
        )
    )
    teaching.invigilators = {
        p["paper_ref"]: {
            room: {"staff_number": f"STF/{n}{room}", "name": f"Dr. {n} {room}"} for room in ["", *p["extra_rooms"]]
        }
        for n, p in enumerate(shared["papers"])
    }
    response = client.post(f"/api/exam-drafts/{draft_id}/publish")
    if expect_ok:
        ok(response)
    else:
        assert response.status_code == 422 and response.json()["error"]["code"] == "UNKNOWN_LECTURER"


def _act(client: TestClient, term_id: str, action: str, at: str | None = None):
    return client.post(f"/api/terms/{term_id}/exam-switch", json={"action": action, **({"at": at} if at else {})})


def test_the_switch_needs_a_published_exam_version(client, teaching, smarttt: FakeSmarttt):
    sign_in(client)
    term_id, _first, _last = _smarttt_term(client, teaching)
    for action in ("schedule_switch", "switch_now"):
        refused = _act(client, term_id, action)
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "NO_EXAM_VERSION"
    closing = _act(client, term_id, "close_now")
    assert closing.status_code == 409 and closing.json()["error"]["code"] == "NOT_SWITCHED"
    assert smarttt.exam_mode_calls == []


def test_a_term_only_in_the_generator_cant_switch(client, teaching):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    refused = _act(client, term_id, "switch_now")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "NOT_IN_SMARTTT"


def test_schedule_move_cancel_and_switch_now(client, teaching, smarttt: FakeSmarttt, db: Session):
    sign_in(client)
    term_id, first, _last = _smarttt_term(client, teaching)
    _publish_exams(client, teaching, term_id)
    state = ok(client.get(f"/api/terms/{term_id}/exam-switch"))
    assert state["status"] == "teaching" and state["published_version"] == 1
    assert state["defaults"]["switch_at"] == f"{first.isoformat()}T00:00:00+03:00"

    # Scheduled for the first exam day at 00:00 (campus time) unless another time is given.
    state = ok(_act(client, term_id, "schedule_switch"))
    assert state["status"] == "scheduled" and state["switch_at"] == f"{first.isoformat()}T00:00:00+03:00"
    assert state["label"].startswith("Scheduled for ")
    assert smarttt.exam_mode_calls[-1] == {
        "term_id": TERM["id"],
        "action": "schedule_switch",
        "at": f"{first.isoformat()}T00:00:00+03:00",
        "by": f"Dee Director ({DIRECTOR})",
    }
    # Moved to the evening before; a time in the past is refused.
    evening = datetime.combine(first - timedelta(days=1), datetime.min.time()).replace(hour=18).isoformat() + "+03:00"
    assert ok(_act(client, term_id, "schedule_switch", evening))["switch_at"] == evening
    assert _act(client, term_id, "schedule_switch", "2020-01-01T00:00:00+03:00").status_code == 422
    # Cancelled: SMARTTT shows teaching again.
    assert ok(_act(client, term_id, "cancel_switch"))["status"] == "teaching"
    # Switched now: everyone sees exams at once.
    state = ok(_act(client, term_id, "switch_now"))
    assert state["status"] == "switched" and state["switched_by"] == f"Dee Director ({DIRECTOR})"
    assert state["label"].startswith("Switched on ") and "by Dee Director" in state["label"]
    # SMARTTT refuses cancelling a switch that has happened.
    late = _act(client, term_id, "cancel_switch")
    assert late.status_code == 409 and late.json()["error"]["code"] == "ALREADY_SWITCHED"

    actions = [a.action for a in db.scalars(select(AuditLog).where(AuditLog.action.like("exam_mode.%")))]
    assert actions == [
        "exam_mode.schedule_switch",
        "exam_mode.schedule_switch",
        "exam_mode.cancel_switch",
        "exam_mode.switch_now",
    ]


def test_close_the_exam_period_scheduled_or_now(client, teaching, smarttt: FakeSmarttt):
    sign_in(client)
    term_id, _first, last = _smarttt_term(client, teaching)
    _publish_exams(client, teaching, term_id)
    ok(_act(client, term_id, "schedule_switch"))
    # Scheduled for the day after the last paper unless another time is given.
    state = ok(_act(client, term_id, "schedule_close"))
    day_after = (last + timedelta(days=1)).isoformat()
    assert state["close_at"] == f"{day_after}T00:00:00+03:00" and state["status"] == "scheduled"
    assert ok(_act(client, term_id, "cancel_close"))["close_at"] is None
    # Closed now: SMARTTT goes back to the teaching timetable.
    ok(_act(client, term_id, "switch_now"))
    state = ok(_act(client, term_id, "close_now"))
    assert state["status"] == "closed" and state["closed_by"] == f"Dee Director ({DIRECTOR})"
    assert state["label"].startswith("Closed on ")
    assert smarttt.exam_mode["mode"] == "teaching"


def test_the_exam_version_goes_to_smarttt(client, teaching, smarttt: FakeSmarttt, db: Session):
    sign_in(client)
    term_id, first, _last = _smarttt_term(client, teaching)
    _publish_exams(client, teaching, term_id)
    [payload] = smarttt.exam_payloads
    assert payload["term_id"] == TERM["id"] and payload["version"] == 1 and payload["based_on_version"] is None
    assert payload["exam_start"] == first.isoformat()
    assert all(p["start_time"] in ("08:30", "11:30", "14:30") for p in payload["papers"])
    assert all(len([s for s in p["seating"] if s["role"] == "main"]) >= 1 for p in payload["papers"])
    exams = ok(client.get(f"/api/terms/{term_id}/exams"))
    assert exams["publications"][0]["sent_to_smarttt"] is True


def test_smarttt_down_leaves_the_version_approved_to_send_later(client, teaching, smarttt: FakeSmarttt):
    sign_in(client)
    term_id, _first, _last = _smarttt_term(client, teaching)
    smarttt.down = True
    try:
        _publish_exams(client, teaching, term_id)
    finally:
        smarttt.down = False
    publication = ok(client.get(f"/api/terms/{term_id}/exams"))["publications"][0]
    assert publication["sent_to_smarttt"] is False and publication["not_sent_reason"]
    sent = ok(client.post(f"/api/terms/{term_id}/exam-publications/1/send"))
    assert sent["smarttt"]["sent"] is True and len(smarttt.exam_payloads) == 1
    again = client.post(f"/api/terms/{term_id}/exam-publications/1/send")
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_SENT"


def test_smarttt_refusing_the_exam_version_approves_nothing(client, teaching, smarttt: FakeSmarttt):
    sign_in(client)
    term_id, _first, _last = _smarttt_term(client, teaching)
    smarttt.refuse_exams = {
        "code": "unknown_lecturer",
        "detail": "SMARTTT doesn't know 1 staff numbers.",
        "staff_numbers": ["STF/0"],
    }
    try:
        _publish_exams(client, teaching, term_id, expect_ok=False)
    finally:
        smarttt.refuse_exams = None
    assert ok(client.get(f"/api/terms/{term_id}/exams"))["publications"] == []
