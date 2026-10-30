from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import sign_in
from tests.fake_smarttt import JANE, TERM, snapshot_data


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()["data"]


def setup_term(client: TestClient) -> str:
    """Open the term, snapshot, import, set hours, propose groups: ready to solve."""
    term = ok(client.post("/api/terms", json={"smarttt_term_id": TERM["id"]}))
    ok(client.post(f"/api/terms/{term['id']}/snapshots"))
    ok(client.post(f"/api/terms/{term['id']}/setup/import"))
    for offering in ok(client.get(f"/api/terms/{term['id']}/offerings")):
        body: dict[str, Any] = {"weekly_hours": 3, "session_length": 3}
        if offering["unit_code"] == "SMED 100":
            body = {"weekly_hours": 2, "session_length": 2, "room_type": "lab"}
        ok(client.patch(f"/api/offerings/{offering['id']}", json=body))
    ok(client.post(f"/api/terms/{term['id']}/groups/propose", json={}))
    return str(term["id"])


def test_only_the_directorate_signs_in(client, smarttt):
    response = client.post("/api/auth/login", json={"identifier": "lecturer", "password": "right-password"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_TIMETABLING_OFFICE"
    sign_in(client)
    assert ok(client.get("/api/auth/me"))["timetabling_office"] is True


def test_import_builds_class_rows_and_offerings(client, smarttt):
    sign_in(client)
    term = ok(client.post("/api/terms", json={"smarttt_term_id": TERM["id"]}))
    snapshot = ok(client.post(f"/api/terms/{term['id']}/snapshots"))
    assert snapshot["counts"]["rooms"] == 5
    result = ok(client.post(f"/api/terms/{term['id']}/setup/import"))
    assert result == {
        "class_rows_created": 2,
        "offerings_created": 4,
        "unresolved": [],
        "rooms_created": 5,
    }
    # Departments come from Attendance; SMARTTT's lecturer numbers fill their counts (H9).
    departments = {d["id"]: d for d in ok(client.get("/api/departments"))["departments"]}
    assert {i: d["lecturer_count"] for i, d in departments.items()} == {1: 4, 2: 4}
    again = ok(client.post(f"/api/terms/{term['id']}/setup/import"))
    assert again["class_rows_created"] == 0  # idempotent: nothing duplicated

    rows = ok(client.get(f"/api/terms/{term['id']}/class-rows"))
    assert {r["label"]: r["student_count"] for r in rows} == {"BED.MATH/CHEM Y1S1": 150, "BSC.COMP SCI Y1S1": 90}
    offerings = {o["unit_code"]: o for o in ok(client.get(f"/api/terms/{term['id']}/offerings"))}
    assert len(offerings["COSC 103"]["class_rows"]) == 2  # shared by both programmes
    assert offerings["COSC 103"]["weekly_hours"] is None  # never invented: the Director sets it

    readiness = ok(client.get(f"/api/terms/{term['id']}"))["readiness"]
    assert readiness["ready"] is False
    assert {p["code"] for p in readiness["problems"]} >= {"offering_hours", "offering_groups"}


def test_group_proposal_splits_by_largest_room(client, smarttt):
    sign_in(client)
    term_id = setup_term(client)
    offerings = {o["unit_code"]: o for o in ok(client.get(f"/api/terms/{term_id}/offerings"))}
    # COSC 103: 240 students, largest lecture hall 200 -> two groups.
    cosc103 = offerings["COSC 103"]
    assert [g["label"] for g in cosc103["groups"]] == ["GR A", "GR B"]
    assert all(g["student_count"] <= 200 for g in cosc103["groups"])
    # SMED 100: 150 students in labs of 40 -> one row split into parallel groups.
    assert len(offerings["SMED 100"]["groups"]) == 4
    assert ok(client.get(f"/api/terms/{term_id}"))["readiness"]["ready"] is True


def test_director_edits_a_group(client, smarttt):
    sign_in(client)
    term_id = setup_term(client)
    offering = next(o for o in ok(client.get(f"/api/terms/{term_id}/offerings")) if o["unit_code"] == "COSC 110")
    group = offering["groups"][0]
    row = offering["class_row_ids"][0]
    edited = ok(
        client.patch(
            f"/api/groups/{group['id']}", json={"label": "GR X", "members": [{"class_row_id": row, "students": 85}]}
        )
    )
    assert edited["label"] == "GR X" and edited["student_count"] == 85
    stranger = client.patch(
        f"/api/groups/{group['id']}",
        json={"label": "GR X", "members": [{"class_row_id": "00000000-0000-0000-0000-000000000000", "students": 5}]},
    )
    assert stranger.status_code == 422


def test_run_publish_flow(client, smarttt):
    sign_in(client)
    term_id = setup_term(client)
    run = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))
    assert run["status"] == "succeeded", run["failure"]
    draft_id = run["draft_id"]

    grid = ok(client.get(f"/api/drafts/{draft_id}?view=row"))
    assert grid["draft"]["violation_count"] == 0
    assert grid["draft"]["publishable"] is True
    labels = [e["label"] for e in grid["entities"]]
    assert labels == ["BED.MATH/CHEM Y1S1", "BSC.COMP SCI Y1S1"]
    assert ok(client.get(f"/api/drafts/{draft_id}?view=room"))["entities"]
    assert ok(client.get(f"/api/drafts/{draft_id}?view=department"))["entities"][0]["label"] in (
        "Computer Science",
        "Education",
    )

    published = ok(client.post(f"/api/drafts/{draft_id}/publish", json={}))
    assert published["version"] == 1
    payload = smarttt.payloads[-1]
    assert payload["based_on_version"] is None
    session = next(s for s in payload["sessions"] if s["key"] == "COSC103-GRA-1")
    assert session["unit_id"] == 101 and session["group_label"] == "GR A"
    assert session["day_of_week"] in ("MON", "TUE", "WED", "THU", "FRI")
    assert session["class_rows"][0]["year_of_study"] == 1

    locked = client.post(f"/api/drafts/{draft_id}/publish", json={})
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "DRAFT_LOCKED"
    copy = ok(client.post(f"/api/drafts/{draft_id}/copy"))
    second = ok(client.post(f"/api/drafts/{copy['id']}/publish", json={}))
    assert second["version"] == 2 and smarttt.payloads[-1]["based_on_version"] == 1
    overview = ok(client.get(f"/api/terms/{term_id}"))
    assert [p["version"] for p in overview["publications"]] == [2, 1]


def test_manual_move_is_checked_and_pins(client, smarttt):
    sign_in(client)
    term_id = setup_term(client)
    draft_id = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))["draft_id"]
    grid = ok(client.get(f"/api/drafts/{draft_id}?view=row"))
    bsc = next(e for e in grid["entities"] if e["label"].startswith("BSC"))
    first, second = bsc["cells"][0], bsc["cells"][1]

    clash = client.patch(
        f"/api/drafts/{draft_id}/sessions/{second['key']}",
        json={"day": first["day"], "start_time": first["start_time"]},
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["details"]["violations"][0]["rule"] in ("H1", "H2")

    lab = client.patch(f"/api/drafts/{draft_id}/sessions/{first['key']}", json={"room_id": "r-lab-1"})
    assert lab.status_code == 409  # wrong room type / too small

    # Move to the first hour where the row and the room are both free; each
    # refused attempt on the way must name the rule it would break.
    target = moved = None
    for day in ("FRI", "THU", "WED", "TUE", "MON"):
        for hour in range(8, 17):
            attempt = client.patch(
                f"/api/drafts/{draft_id}/sessions/{first['key']}", json={"day": day, "start_time": f"{hour:02d}:00"}
            )
            if attempt.status_code == 200:
                target, moved = (day, f"{hour:02d}:00"), attempt.json()["data"]
                break
            assert attempt.json()["error"]["details"]["violations"][0]["rule"]
        if target:
            break
    assert target is not None and moved is not None
    assert moved["violation_count"] == 0
    assert moved["pinned"] == 1

    rerun = ok(client.post(f"/api/drafts/{draft_id}/resolve", json={"time_limit_s": 20}))
    assert rerun["status"] == "succeeded", rerun["failure"]
    new = ok(client.get(f"/api/drafts/{rerun['draft_id']}?view=row"))
    cell = next(c for e in new["entities"] for c in e["cells"] if c["key"] == first["key"])
    assert (cell["day"], cell["start_time"], cell["pinned"]) == (*target, True)


def test_publish_refused_by_smarttt_is_reported(client, smarttt):
    sign_in(client)
    term_id = setup_term(client)
    draft_id = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))["draft_id"]
    smarttt.refuse_publish = {"code": "lecturer_clash", "detail": "An allocated lecturer would be double-booked."}
    response = client.post(f"/api/drafts/{draft_id}/publish", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LECTURER_CLASH"
    assert ok(client.get(f"/api/terms/{term_id}"))["publications"] == []


def test_run_refused_until_ready(client, smarttt):
    sign_in(client)
    term = ok(client.post("/api/terms", json={"smarttt_term_id": TERM["id"]}))
    ok(client.post(f"/api/terms/{term['id']}/snapshots"))
    ok(client.post(f"/api/terms/{term['id']}/setup/import"))
    response = client.post("/api/runs", json={"term_id": term["id"]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_READY"


def test_infeasible_run_is_explained(client, smarttt):
    sign_in(client)
    term_id = setup_term(client)
    rows = ok(client.get(f"/api/terms/{term_id}/class-rows"))
    bsc = next(r for r in rows if r["label"].startswith("BSC"))
    # Make BSC available only one hour a week; its two 3-hour units can't fit.
    ok(client.patch(f"/api/class-rows/{bsc['id']}", json={"unavailable": list(range(59))}))
    run = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 15}))
    assert run["status"] == "failed"
    assert run["failure"]["reasons"]
    assert any(
        "BSC.COMP SCI" in r["message"] or "BSC.COMP SCI" in r.get("entity", "") for r in run["failure"]["reasons"]
    )


def test_repair_keeps_published_and_lecturers(client, smarttt):
    sign_in(client)
    term_id = setup_term(client)
    run = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))
    ok(client.post(f"/api/drafts/{run['draft_id']}/publish", json={}))
    published = smarttt.payloads[-1]["sessions"]

    # SMARTTT now reports that version with Jane on two classes.
    as_published = []
    for s in published:
        lecturer = JANE if s["key"] in ("COSC103-GRA-1", "COSC110-MAIN-1") else None
        as_published.append({**s, "section_key": s["key"], "lecturer_id": lecturer})
    smarttt.snapshot = snapshot_data(published=as_published, version=1)
    ok(client.post(f"/api/terms/{term_id}/snapshots"))

    repair = ok(client.post("/api/runs", json={"term_id": term_id, "mode": "repair", "time_limit_s": 20}))
    assert repair["status"] == "succeeded", repair["failure"]
    assert repair["soft_scores"]["moved"] == 0  # nothing changed, so nothing moves
    second = ok(client.post(f"/api/drafts/{repair['draft_id']}/publish", json={}))
    assert second["version"] == 2


def test_pdf_export(client, smarttt):
    sign_in(client)
    term_id = setup_term(client)
    draft_id = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))["draft_id"]
    for view in ("row", "room", "department"):
        response = client.get(f"/api/drafts/{draft_id}/export.pdf?view={view}")
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")
    assert (
        "teaching-timetable-2026-2027-S1-row.pdf"
        in client.get(f"/api/drafts/{draft_id}/export.pdf").headers["content-disposition"]
    )


def test_writes_need_csrf(client, smarttt):
    sign_in(client)
    del client.headers["X-XSRF-TOKEN"]
    response = client.post("/api/terms", json={"smarttt_term_id": TERM["id"]})
    assert response.status_code == 403


def test_rooms_for_manual_moves_are_the_active_ones(client, smarttt):
    sign_in(client)
    term = ok(client.post("/api/terms", json={"smarttt_term_id": TERM["id"]}))
    assert client.get(f"/api/terms/{term['id']}/rooms").status_code == 409  # no snapshot yet
    ok(client.post(f"/api/terms/{term['id']}/snapshots"))
    codes = [r["code"] for r in ok(client.get(f"/api/terms/{term['id']}/rooms"))]
    assert "OLD 1" not in codes
    assert codes == sorted(codes, key=lambda c: (c.split()[0], c))
