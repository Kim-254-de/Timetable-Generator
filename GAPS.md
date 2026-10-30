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

---

## For the frontend team (raised by the backend)

<!-- Add F-<n> entries here: endpoints or fields added, renamed or removed; changed error codes,
     enums, auth or limits; anything a screen now shows wrongly; anything you noticed in the UI. -->

_Nothing yet._
