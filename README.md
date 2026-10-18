# Timetable Generator

Tharaka University's teaching-timetable generator, run by the Directorate of
Examinations and Timetabling. It decides when and where every class meets
(group splits, room, day, time) with a constraint solver (OR-Tools CP-SAT),
lets the Director review and adjust the result, and publishes the approved
version to SMARTTT. Departments then allocate lecturers in the Timetable
Allocator.

The Generator talks **only to SMARTTT** (never to the Allocator), over
SMARTTT's `/api/v1/integrations/generator/` endpoints with its own
`X-API-Key`. See `SYSTEM_HANDOFF.md` for the whole platform.

## Workflow

1. **Open a term** (a SMARTTT term) and **take a snapshot** of SMARTTT's master
   data: rooms, departments with lecturer counts, programmes, units, curricula,
   class sizes, and the current published timetable with its lecturers.
2. **Import** class rows and units from the snapshot. Weekly hours, session
   length and room type are prefilled from the last published timetable where
   the unit is in it; otherwise the Director sets them. Nothing is invented.
3. **Propose groups**: each unit is split so every group fits the largest room
   of its type. The Director decides the final split.
4. **Run** the solver in the background (a time limit, default 10 minutes).
   Each successful run is a new draft; failures say which rule and which class
   row, room size or department made it impossible.
5. **Review** the draft as grids per class row, room or department, with the
   soft-constraint scores. **Drag a class** to another hour, or change its room;
   every move is checked against the hard rules and refused with the reason if
   it breaks one. Moved classes are pinned. **Re-solve** around the pins.
6. **Approve and publish**: the draft becomes the term's next numbered version
   in SMARTTT. Students see room and time; lecturers come from the Allocator.
7. **Mid-term change**: take a new snapshot and run a **repair**. It keeps every
   session where it was unless a rule forces a move, and never moves a class
   onto an hour its allocated lecturer already teaches (H13).

## Rules

Hard (never broken): H1 one class per room per hour; H2 one class per class row
per hour; H3 room big enough; H4 right room type; H5 every session scheduled
once; H6 multi-hour sessions consecutive, same day and room; H7 Monday-Friday
07:00-19:00 only; H8 not when the room or class row is unavailable; H9 a
department runs at most as many classes at once as it has lecturers; H10 pinned
sessions stay; H13 (repairs) allocated lecturers stay clash-free.

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

## Checks

```bash
cd backend && ruff check . && ruff format --check . && mypy app && pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

## Access

Only members of SMARTTT's `timetabling_office` group (the Directorate) can sign
in. Sessions, CSRF and rate limiting work as in the Allocator.
