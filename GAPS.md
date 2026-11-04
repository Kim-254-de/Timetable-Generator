# Gaps between frontend and backend

A two-way list between the frontend lead and the backend team. Each side adds what it finds;
neither side deletes the other's entries. How to use it is in `CLAUDE.md`.

Entry format:

```
### B-<n> · <High|Medium|Low> · <one-line title>
- **Raised:** <YYYY-MM-DD>, <who>   **Status:** open | in progress | done (<commit>) | won't do (<why>)
- **Seen:** what is missing or different, with file paths, endpoints, commits.
- **Why it matters:** which screen or user is affected.
- **Done when:** the check that closes it.
```

Use `B-` for items the backend should act on, and `F-` for items the frontend should act on.

---

## For the backend team (raised by the frontend)

### B-1 · Medium · SMARTTT terms and snapshot calls fail against SMARTTT `main`
- **Raised:** 2026-10-25, frontend (Wayler)   **Status:** open
- **Seen:** sign-in now goes through Smart Attendance (`62533da`), but
  `backend/app/clients/smarttt.py` still calls `generator/terms/` (`api/routes.py:128`) and
  `generator/snapshot/` (`services/setup.py:288`) under `/api/v1/integrations/`. SMARTTT
  `origin/main` serves only `generator/publish/`. (Also logged as B-1 in SMARTTT_BACKEND `GAPS.md`.)
- **Why it matters:** the SMARTTT term picker and "Import from SMARTTT" in the web UI fail
  against SMARTTT `main`.
- **Done when:** both work against SMARTTT `main`, or the calls are removed and the UI no
  longer offers them (tell us under "For the frontend team" so we can remove the buttons).

### B-2 · Medium · Which branch is current: `PK` or `main`?
- **Raised:** 2026-10-25, frontend (Wayler)   **Status:** open
- **Seen:** `origin/main` imports department teaching from Smart Attendance
  (`clients/attendance.py`, `e533fe6`) and signs in through it (`62533da`). `origin/PK` still
  reads from the Timetable Allocator, and has one commit that isn't on `main`: `997e20b`
  "Seat exams at 90% everywhere, name extra invigilators, and switch SMARTTT to exams".
  Frontend work goes on `wayler`, branched from `main`.
- **Why it matters:** frontend changes must land on the branch that ships, and `997e20b`'s
  exam screens aren't on `main` yet.
- **Done when:** `997e20b` is merged into `main` (or dropped), and this entry confirms `main`
  is the branch to build on.

### B-3 · Low · Is the Timetable Allocator retired?
- **Raised:** 2026-10-25, frontend (Wayler)   **Status:** open
- **Seen:** department teaching, exam papers and invigilators moved into the Smart Attendance
  department portal on 2026-10-25. The Allocator's `README.md` and `SYSTEM_HANDOFF.md` here
  still describe the Allocator as the departments' system.
- **Why it matters:** the Allocator frontend has the same screens as Attendance, so a fix
  could land in the wrong app.
- **Done when:** the Allocator repo is archived (or its README says what it's still for),
  and `SYSTEM_HANDOFF.md` describes the Attendance flow.

### B-4 · High · Reserved venues work for health only: a new course with its own rooms can't be set up
- **Raised:** 2026-11-03, frontend (Wayler)   **Status:** open
- **Seen:** "health" is the only course that can have rooms of its own, and it is built into
  the code rather than set up as data:
  - one fixed category: `HEALTH` in `backend/app/exam_solver/model.py:50-51`, chosen by
    `paper_kind()` (`model.py:54-66`) from one prefix list per term,
    `Term.exam_health_prefixes` (`app/models.py:109`, default list in
    `services/exam_health.py:38`);
  - one yes/no room flag: `ExamRoom.health` / `Room.health_unit` (`app/models.py:170`), read
    from SMARTTT's `health_unit` (`services/master.py:199,215`);
  - two rules that name health: H-E9, the health unit holds health papers and only them
    (`exam_solver/sessions.py:126-138`, `exam_solver/rooms.py:68,91,122`), and H-E8,
    health papers (with common and postgraduate ones) sit first or last in a day
    (`model.py:195`), where only health has rooms of its own.
  **Example to test against:** the university starts a new Bachelor of Engineering. Its papers
  (codes starting `BENG`) must be sat only in the engineering workshops, W1 and W2, and no
  other course's paper may be put in W1 or W2.
  The same goes for a School of Law whose papers (`LAW`) must be sat in the law school's own
  rooms: it should be a second group set up on screen, not a `Law.tsx` or new solver code.
  Today the only ways to do this are wrong: pinning each BENG paper to W1 by hand on every
  draft (and nothing stops other papers going into W1), or calling BENG "health" (then BENG
  shares the health unit's rooms and seats, and only sits first or last).
- **What we ask for:** turn the health unit into the first of any number of **reserved venue
  groups**. A group has a name, its rooms (set in SMARTTT, see SMARTTT_BACKEND `GAPS.md`
  B-3), the code prefixes of its papers (per exam period, set by the Director, as health's
  are now), and two rules that can be turned on per group: "these rooms are for this group
  only" and "first or last session of a day only". Health becomes a group with both rules
  on and today's prefixes, so nothing changes for health. The shape is yours to choose; one
  way:
  ```
  (the seat numbers are made up)
  GET /api/terms/{id}/exam-period ->
    "venue_groups": [
      { "group": "health", "name": "Health unit", "prefixes": ["NURS", "BMLS", ...],
        "own_rooms_only": true, "first_or_last_only": true, "seats": 420 },
      { "group": "engineering", "name": "Engineering workshops", "prefixes": ["BENG"],
        "own_rooms_only": true, "first_or_last_only": false, "seats": 80 } ]
  PATCH /api/terms/{id}/exam-period  { "venue_groups": [ { "group": "engineering", "prefixes": ["BENG"] } ] }
  ```
  A paper's category on the Exams tab can then be any group as well as regular, common and
  postgraduate. The Director's health-letter upload stays as it is.
- **Why it matters:** each new course with its own venue would otherwise need a code change in
  three systems. Until then its papers are put in any room, and other papers go into its rooms.
- **Done when:** the example above works with no code change: the admin puts W1 and W2 in an
  "Engineering workshops" group, the Director adds `BENG` to it for the exam period, a
  generated draft sits every BENG paper in W1 or W2 and nothing else there; and a health
  draft is the same as before. Tell us the shapes under "For the frontend team" so we can
  build the Exams-tab and Venues-page screens (that part is ours).

### B-5 · Medium · A health paper whose prefix isn't on the list quietly becomes an ordinary paper
- **Raised:** 2026-11-03, frontend (Wayler)   **Status:** open
- **Seen:** in the health-letter review (`services/exam_health.py:165`), a paper is health only
  if its code prefix is on the term's list; otherwise it is `"regular"`. A new health course
  (say `BSCN 101`) in the letter, with its class heading "BSC NURSING Y1S1", is saved as an
  ordinary paper. The review shows the category per line, but nothing points it out.
- **Why it matters:** the Director is likely to miss one line among dozens. The paper is then
  seated in general rooms, at any time of day, and the health unit's seats are planned
  without it.
- **Done when:** the review's `summary` lists the prefixes in the letter that will be saved as
  ordinary papers, with their lines, for example
  `"not_health": [{ "prefix": "BSCN", "lines": [12, 13] }, { "prefix": "MATH", "lines": [40] }]`.
  Some are right (MATH 101 is ordinary); the Director sees them all at once and adds the ones
  that aren't. We'll show them above the review as "These will be ordinary papers: BSCN (2),
  MATH (1)", with "Add to the health list" next to each (that part is ours).

---

## For the frontend team (raised by the backend)

<!-- Add F-<n> entries here: endpoints or fields added, renamed or removed; changed error codes,
     enums, auth or limits; anything a screen now shows wrongly; anything you noticed in the UI. -->

_Nothing yet._
