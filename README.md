# Timetable Generator

Tharaka University's teaching-timetable generator, run by the Directorate of
Examinations and Timetabling. It decides when and where every class meets
(group splits, room, day, time) with a constraint solver (OR-Tools CP-SAT),
lets the Director review and adjust the result, approves it, and provides the
timetable as **PDF, Word and Excel** downloads.

**Departments enter their teaching first**, in the Timetable Allocator: their
courses (class rows), units, group splits and each group's lecturer, which
they publish to the Director. The Director **imports** what is published
(`ALLOCATOR_BASE_URL`, `ALLOCATOR_CLIENT_KEY`), adds the lecture halls,
generates and publishes; SMARTTT receives the timetable with the lecturers in
it, in one publish. Imported class rows, units and groups are read-only here
("edit this in the Allocator"); a class row's unavailable hours, the rooms and
the term settings stay the Director's. Rows can still be entered here for
units no department enters.

SMARTTT is optional: its data can be imported to pre-fill the same screens,
and an approved timetable is sent to it (over SMARTTT's
`/api/v1/integrations/generator/` endpoints, `X-API-Key`) when it is connected.
The Timetable Allocator reads each term and, once published, each class's
day, time and room (`/api/integrations/allocator/terms[/{id}/times]`) with its
own key (`ALLOCATOR_API_KEY`).
See `SYSTEM_HANDOFF.md` for the whole platform.

## Workflow

1. **Create a term** (academic year, semester 1–3, the name and version line
   printed on the timetable), optionally copying a previous term's class rows,
   units and groups.
2. **Enter the data**, one at a time or with **Paste from Excel** (a template
   is downloadable on each screen):
   - **Lecture halls**: code, building, capacity, type (lecture hall, lab,
     seminar room), available or closed, blocked hours. Shared by every term.
   - **Departments**: code, name, school, number of lecturers (caps how many of
     its classes run at once). Shared by every term.
   - **Class rows**: programme, year, study semester, sub class, department,
     number of students, unavailable hours.
   - **Units**: code, title, owning department, hours per week, class length,
     room type, and the class rows that take it. A new unit starts as one whole
     class.
   (Or, for a SMARTTT term, **import** rooms, departments, class rows and units
   from a SMARTTT snapshot; anything already entered is kept.)
   **Departments** tab: **Import published departments** brings in what
   departments published in the Allocator (class rows, units, groups with
   lecturers); importing again updates in place and lists what changed. The
   tab shows which departments have and haven't published; you can generate
   without the missing ones.
3. **Propose groups** (units entered here only): each unit is split so every
   group fits the largest room of its type. Departments split their own units.
4. **Run** the solver in the background (a time limit, default 10 minutes).
   Each successful run is a new draft; failures say which rule and which class
   row, room size or department made it impossible.
5. **Review** the draft as grids per class row, room or department, with the
   soft-constraint scores. **Drag a class** to another hour, or change its room;
   every move is checked against the hard rules and refused with the reason if
   it breaks one. Moved classes are pinned. **Re-solve** around the pins.
   A department imported **after** publishing: copy the published draft, tick
   **Keep the published classes** and re-solve; its classes are added and no
   published class moves.
6. **Approve and publish**: the draft becomes the term's next numbered version.
   It is sent to SMARTTT when SMARTTT is connected, each session with its
   lecturer (`lecturer_staff_number`, `lecturer_name`); otherwise it is marked
   "not yet in SMARTTT" and still counts as approved for downloads and the
   Allocator, where departments see each class's day, time and room.
7. **Download** any draft or version as **PDF**, **Word (.docx)** or
   **Excel (.xlsx)**, by class row, lecture hall or department, in the
   Directorate's layout (header, Mon–Fri × 07:00–19:00 grid, "UNIT / GR / ROOM"
   cells with the lecturer, version line, "Prepared by … Director Examination & Timetabling").
8. **Mid-term change**: edit the data (or take a new snapshot) and run a **repair**. It keeps every
   session where it was unless a rule forces a move, and never moves a class
   onto an hour its lecturer already teaches (H13).

## Needs from SMARTTT

Not built in these two repos; SMARTTT needs these for the department-first flow:

- **Accept lecturers on publish**: `generator/publish/` takes
  `lecturer_staff_number` (and `lecturer_name`) per session, and refuses the
  publish naming the staff numbers it doesn't know.
- **Add lecturers it doesn't know**: a way to create them (staff number, name,
  department, FT/PT), so a department's new lecturer can be published.
- **Match by code**: units, rooms and programmes are now typed in by
  departments and the Director, so SMARTTT matches them by code (`unit_code`,
  `room_code`, programme code and year/semester), not by SMARTTT ids.

## Rules

Hard (never broken): H1 one class per room per hour; H2 one class per class row
per hour; H3 room big enough; H4 right room type; H5 every session scheduled
once; H6 multi-hour sessions consecutive, same day and room; H7 Monday-Friday
07:00-19:00 only; H8 not when the room or class row is unavailable; H9 a
department runs at most as many classes with no lecturer named at once as it
has lecturers; H10 pinned sessions stay; H13 a lecturer (one staff number,
across every department) teaches one class at a time, from the first solve.
Before solving, the pre-check names a lecturer given more hours than the week
has and a group larger than every room of its type.

A class row split across groups of one unit (GR A, GR B ...) may have the
groups meet together or in turn, e.g. rotating labs; each student attends only
their own group, and the row's other classes keep clear of all of them.

Soft (weighted, tunable per run): S1 gaps, S2 a group twice in a day, S3 more
than 5 hours a day, S4 07:00 and after 17:00, S5 department peaks, S6 building
changes, S7 empty seats, S8 (repairs) moving published sessions.

## Solver

`app/solver/` is plain Python with no database: `model.py` (the problem),
`precheck.py` (counting checks that explain impossible inputs), `cpsat.py`
(phase 1 time, phase 2 rooms, infeasibility cores), `validate.py` (independent
hard-rule check of any timetable), `scoring.py`, `groups.py` (group proposal).

### Benchmark: September-December 2026

`tools/pdf_timetable.py` reads the Directorate's 62-page PDF into
`tests/fixtures/sep_dec_2026.json`; `tools/benchmark.py` re-solves it from
scratch and compares with the hand-made timetable on the same rules. Room
sizes, room types and lecturer counts are not in the PDF, so the benchmark
leaves H3/H4 out and takes each department's peak from the hand-made timetable
(stated in the tool). On a 4-core laptop with a 570 s limit:

| | Hand-made | Solver |
|---|---|---|
| Hard-rule violations | 0 | 0 |
| One-hour gaps | 55 | 31 |
| Sessions starting at 07:00 | 411 | 258 |
| Sessions starting at 15:00 or later | 411 | 285 |
| Session-hours at 07:00 or after 17:00 | 1206 | 718 |
| Extra buildings in a day | 1075 | 536 |
| Time | | 573 s |

405 class rows, 1663 sessions, 102 rooms. Re-run with
`python -m tools.benchmark --time-limit 570 --workers 8`, or `pytest -m benchmark`.

## Layout

```
backend/    FastAPI + SQLAlchemy 2 + Alembic (PostgreSQL), RQ worker (Redis), OR-Tools CP-SAT
  app/solver/       the solver (no database)
  app/services/     setup, grouping, runs, drafts and publishing, PDF export
  app/worker/       RQ job entry points
  tools/            PDF extraction and the benchmark
frontend/   React 19 + Vite + TanStack Query + Tailwind v4: terms, setup, runs, draft grids with drag and drop
```

## Running locally

Backend (Python 3.12), API and worker:

```bash
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp ../.env.example .env        # DATABASE_URL, REDIS_URL, SMARTTT_BASE_URL, SMARTTT_API_KEY,
                               # ENVIRONMENT=development, COOKIE_SECURE=false
alembic upgrade head
uvicorn app.main:app --port 8002 --reload
rq worker generator-runs --url redis://localhost:6379/0     # in another terminal
```

Without Redis, `RUN_INLINE=true` solves inside the API request (development only;
refused in production). Frontend: `cd frontend && npm install && npm run dev`
(proxies `/api` to port 8002). Everything in containers: `docker compose up --build`,
then http://localhost:8081.

## Deploying with Docker

On a Linux server with Docker and the Compose plugin:

```bash
cp .env.example .env     # fill in POSTGRES_PASSWORD, SMARTTT_*, ALLOCATOR_API_KEY, ALLOCATOR_BASE_URL, ALLOCATOR_CLIENT_KEY;
                         # SOLVER_WORKERS = the server's cores
docker compose up -d --build
```

This runs PostgreSQL, Redis, the API (migrations run as it starts), the solver
worker and the web app on port 8081, all restarting on their own. Then:

- Put an HTTPS proxy (Caddy, nginx, Traefik, or the host's) in front of port 8081;
  sign-in cookies are `Secure` and need HTTPS. Add `Strict-Transport-Security` there.
- Back up the `db-data` volume (or `pg_dump`) on a schedule.
- The Allocator reaches the Generator through this web address
  (`GENERATOR_BASE_URL` there), so the URL must be reachable from its server.
- Update: `git pull && docker compose up -d --build`.

## Checks

```bash
cd backend && ruff check . && ruff format --check . && mypy app && pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

## Dependencies

The image installs `backend/requirements.lock`: every package pinned to the tested
version and checked by hash. After changing `backend/pyproject.toml`, regenerate it
(Linux, Python 3.12, as in the image) and run the checks again:

```bash
cd backend && uv pip compile pyproject.toml --python-version 3.12 \n  --python-platform x86_64-unknown-linux-gnu --generate-hashes --no-header -o requirements.lock
```

## Access

Only members of SMARTTT's `timetabling_office` group (the Directorate) can sign
in. Sessions, CSRF and rate limiting work as in the Allocator.
