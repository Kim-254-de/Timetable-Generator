# Tharaka University Smart Timetabling Platform — Engineering Handoff

> **Audience:** Claude Code (or any engineer) picking up this work.
> **Status as of:** 18 October 2026.
> **Owner:** Peter Kamami (PK) and team.
> **How to use this file:** Read sections 1–3 to understand the platform. Section 4 lists what is broken today. Section 5 is the spec for the new system. Section 7 is the ordered task list, each task with a "Done when" check. Section 8 lists open questions — do not guess answers to them; ask.

---

## 0. Status after the Phase 1–4 build (18 October 2026)

Phases 1–4 are built and committed on local branches (not pushed):

| Repo | Branch | What |
|---|---|---|
| `Kim-254-de/SMARTTT_BACKEND` | `feature/timetabling-integrations` (from `main`) | `allocator/*` and `generator/*` integration endpoints, `Lecturer.employment_type`, `TimetableSlot.session_key/study_semester/publication`, `TimetablePublication`, publish + allocation pushes to Attendance |
| `Kim-254-de/Timetable-Allocator` | `feature/t1-allocator` | Full backend + web UI (T1.1, T1.3–T1.5, T4.3 flags) |
| `Kim-254-de/Timetable-Generator` | `feature/t2-generator` | Solver, backend, worker, web UI, PDF, benchmark (T2.1–T2.5, T3.1–T3.2, T4.1, T4.3) |

**Findings that change this document**

- **C1 is mostly stale.** `Kim-254-de/SMARTTT_BACKEND` `main` is 221 commits ahead of `peter-dri/SMARTTT_BACKEND` and already has `apps/integrations`, `courses`, `notifications`, `schedule`, the reschedule push, and SMARTTT sign-in for Attendance. Treat `Kim-254-de` as the source of truth.
- **The live timetable model is `TimetableSlot`, not `TimetableSession`.** One row per class row per meeting, with `class_group` (GR A…), `stream`, `lecturer` and `lecturer_name_text`. The integrations are built on `TimetableSlot`.
- **Excel upload is gone from `main`** (`apps/uploads` no longer exists; timetables arrive as PDF via `pdf_timetable_parser`), so C4–C6 and H1–H3 in section 4 need re-checking against `main` before anyone fixes them.

**Decisions taken while building (review them)**

1. **Allocation unit = section** (unit + group, e.g. `COSC 103 GR A`, key `"<unit id>-<GROUPKEY|MAIN>"`), not a single meeting: every slot of a section gets the same lecturer. The Allocator API keeps the path names `/sessions/{key}/…` from 5.9; the SMARTTT side is `allocator/sections/…` (5.10 below).
2. **Sign-in:** the new systems do not verify SMARTTT JWTs (that would mean sharing Django's `SECRET_KEY`). Each calls SMARTTT's `…/authenticate/` with its own API key, exactly as Attendance already does, then keeps its own server-side session (hashed token cookie, CSRF, idle/absolute expiry, roles re-read every 5 min via `…/identity/`).
3. **Roles:** COD = `Department.head_of_department`; department staff = `DepartmentAdmin`; Directorate = Django group `timetabling_office` (`TIMETABLING_OFFICE_GROUP`). **Create that group in Django admin and add the Director's office.**
4. **Lecturers stay with SMARTTT across versions.** A publish keeps every section's lecturer and is refused (409 `lecturer_clash`) if the new times would double-book one; the Generator's repair mode avoids that (H13).
5. **First publish over an uploaded timetable** needs `replace_unpublished: true` (a checkbox in the Director's UI), so an upload is never wiped by accident.
6. **Split class rows:** groups of one unit that share a class row may meet together *or* in turn (rotating labs); the row's other classes avoid all of them. (Forcing them together made lab splits infeasible.)
7. **Weekly hours / session length are never invented** (open question 1): prefilled only from the published timetable, otherwise the Director enters them; runs are refused until set. L/P/CF are recorded on each allocation as entered, for the PDF form.
8. **Study semester** is stored separately from the term (`TimetableSlot.study_semester`, `class_rows.study_semester`), as proposed in open question 3.
9. **Teaching days** Monday–Friday only, 07:00–19:00 — enforced by SMARTTT's publish validation as well as the solver.

**Benchmark (T2.5 phase check)** — Sep–Dec 2026 rebuilt from the PDF (405 class rows, 1663 sessions, 102 rooms): 0 hard violations in 573 s on a 4-core laptop; gaps 31 vs 55, 07:00 starts 258 vs 411, starts ≥15:00 285 vs 411 (hand-made). Room sizes/types and lecturer counts are not in the PDF, so H3/H4 are out of the benchmark and H9 uses each department's hand-made peak.

**Still to do (needs people or data)**

- Push the branches and open PRs; deploy with new env vars: SMARTTT `ALLOCATOR_API_KEY`, `GENERATOR_API_KEY`, `TIMETABLING_OFFICE_GROUP`; Allocator/Generator `SMARTTT_API_KEY`, `DATABASE_URL`, (Generator) `REDIS_URL` + an RQ worker.
- Phase checks that need the real system: Computer Science entering its Sep–Dec allocation from `VETTED_SEP-DEC ALLOCATION 2026.docx` (T1 check); the Director's office building one school end to end (T3 check); a live mid-term room change reaching Attendance within a minute (T4 check — the push path is covered by a SMARTTT test).
- Real room capacities and types, and FT/PT on every lecturer (`employment_type` defaults to full-time).
- The older Word-document allocation upload (`timetable/assign-lecturers/`) can still overwrite lecturers on slots it matches. Once departments use the Allocator, retire that upload or make it skip slots allocated there.
- Open questions 1 and 2 (section 8) are still open; the code works either way but the Director must enter hours and room types.

---

## Contents

1. [The platform in one page](#1-the-platform-in-one-page)
2. [Repositories and live services](#2-repositories-and-live-services)
3. [Existing systems as they are today](#3-existing-systems-as-they-are-today)
   - 3.1 SMARTTT backend (Django)
   - 3.2 SMARTTT frontend (Flutter)
   - 3.3 Smart Attendance backend (Node)
   - 3.4 Smart Attendance frontend (React)
   - 3.5 Integration contracts between them
4. [Known problems, by severity](#4-known-problems-by-severity)
5. [New systems: Timetable Generator and Timetable Allocator](#5-new-systems-timetable-generator-and-timetable-allocator)
6. [Business rules already decided](#6-business-rules-already-decided)
7. [Work plan for Claude Code](#7-work-plan-for-claude-code)
8. [Open questions](#8-open-questions)
9. [Conventions and guardrails](#9-conventions-and-guardrails)
10. [Reference data](#10-reference-data)

---

## 1. The platform in one page

Tharaka University (Marimanti, Kenya) wants to move timetabling and attendance from manual (Excel/Word/PDF) to software. The target pipeline is **Timetable Generator → Timetable Allocator → SMARTTT → Smart Attendance**, built from four systems, with SMARTTT as the hub:

```
┌───────────────────────────┐  snapshot of inputs   ┌──────────────────────┐  slots, rooms, rosters  ┌──────────────────────┐
│ TIMETABLE GENERATOR (new) │ ◀──────────────────── │                      │ ──────────────────────▶ │ SMART ATTENDANCE     │
│ repo: Timetable-Generator │ ────────────────────▶ │  SMARTTT (existing)  │ ──────────────────────▶ │ (existing)           │
│ Director of Exams         │  publish timetable    │  Django + Flutter    │  timetable-change push  │ Node + React         │
│ FastAPI + OR-Tools        │                       │                      │                         │ QR/GPS, card,        │
└───────────────────────────┘                       │  Owns master data    │                         │ fingerprint, face    │
┌───────────────────────────┐  published sessions   │  and the published   │                         └──────────────────────┘
│ TIMETABLE ALLOCATOR (new) │ ◀──────────────────── │  timetable           │
│ repo: Timetable-Allocator │ ────────────────────▶ │                      │
│ Departments (CODs)        │  lecturer per session │                      │
│ FastAPI + React           │                       │                      │
└───────────────────────────┘                       └──────────────────────┘
```

The Generator and the Allocator **never call each other**. Both talk only to SMARTTT. The Generator publishes the timetable to SMARTTT; the Allocator reads the published sessions from SMARTTT and writes the lecturer for each session back to SMARTTT.

| System | Repo | Job | Users |
|---|---|---|---|
| **Timetable Generator** (new) | `Kim-254-de/Timetable-Generator` | Decides when and where every class meets: group splits, room, day, time. Uses a constraint solver. | Director of Examinations and Timetabling |
| **Timetable Allocator** (new) | `Kim-254-de/Timetable-Allocator` | Decides who teaches each class: assigns a lecturer to each unit group, after the timetable is published. Replaces the Word allocation form. | Each department's Chair of Department (COD) |
| **SMARTTT** | `peter-dri/SMARTTT_BACKEND`, `Kim-254-de/SMARTTT_fronted` | Master data (units, programmes, rooms, lecturers, students) and the published timetable. Shows each student and lecturer their personal timetable in a Flutter app. | Students, lecturers, admins |
| **Smart Attendance** | `Kim-254-de/ATTENDANCE_backend`, `Kim-254-de/ATTENDANCE_fronted` | Records who attends. A class can only be opened in its timetabled slot, check-ins are fenced to its room, and students are checked against the roster from SMARTTT. | Lecturers, students |

**Key rule:** systems only talk over HTTP APIs with a shared key. No system writes to another system's database.

---

## 2. Repositories and live services

| Repo | Stack | Notes |
|---|---|---|
| `github.com/peter-dri/SMARTTT_BACKEND` | Django 5, DRF, SimpleJWT, PostgreSQL (SQLite in dev), pandas, openpyxl | **Out of date vs production** — see 4.1 |
| `github.com/Kim-254-de/SMARTTT_fronted` | Flutter 3 (Dart ^3.9.2), Riverpod, GoRouter, Dio, Firebase (auth, messaging), SharedPreferences | Builds Android, web, Windows, macOS, Linux. Web hosted on Firebase. |
| `github.com/Kim-254-de/ATTENDANCE_backend` | Node ≥20.11 (ESM), TypeScript 5 strict, Express 5, `pg`, Zod, Argon2id, jose (JWT), Pino, Vitest | Also contains `face-service/` (Python FastAPI + OpenCV) and `mock-erp/` (Node) |
| `github.com/Kim-254-de/ATTENDANCE_fronted` | React 19, TypeScript, Vite, Tailwind v4, TanStack Query, react-hook-form + Zod, MSW mocks, Playwright | Deployed with nginx (Dockerfile + `deploy/default.conf.template`) |
| `github.com/Kim-254-de/Timetable-Generator` *(new, empty)* | Python 3.12, FastAPI, SQLAlchemy + Alembic, PostgreSQL, OR-Tools CP-SAT, Redis + RQ worker; React 19 + Vite web UI | The Director's system — section 5 |
| `github.com/Kim-254-de/Timetable-Allocator` *(new, empty)* | Python 3.12, FastAPI, SQLAlchemy + Alembic, PostgreSQL; React 19 + Vite web UI | The departments' system — section 5 |

**Live hosts referenced in code**

| Host | Referenced by | What it is |
|---|---|---|
| `https://api.nextup.co.ke/api/v1/` | Flutter `lib/core/network/api_client.dart`, `web/admin.html` | Production SMARTTT API used by the app |
| `https://smarttt-backend-n44z.onrender.com` | Attendance `attendance_backend-0004-smarttt-env-example.patch` | SMARTTT on Render free tier (cold starts ~30 s) |

---

## 3. Existing systems as they are today

### 3.1 SMARTTT backend (Django) — `SMARTTT_BACKEND`

**Layout.** `config/` (settings split into `base.py`, `development.py`, `production.py`), `apps/<name>/` with sub-packages `models/ serializers/ services/ views/ validators/ permissions/ selectors/ utils/ tests/`.

**Apps**

| App | Purpose | Key models |
|---|---|---|
| `accounts` | Users, roles, auth views | `User(AbstractUser, BaseModel)`: `role`, `university_id`, `phone_number` |
| `students` | Student records | `Student` (registration_number, program, department, current_study_year, current_semester…), `AcademicProgress`, **`StudentEnrollment` (duplicate — see 4.3)** |
| `lecturers` | Lecturer profile | `Lecturer`: user, department, rank, `max_weekly_teaching_hours` (default 12) |
| `departments` | Faculty → Department | `Faculty`, `Department`, `DepartmentAdmin` |
| `programs` | Programmes | `Program`: department, name, code, duration_years, award_type |
| `units` | Course units | `Unit`: code, name, credit_hours, department |
| `curriculum` | Units per programme/year/semester | `Curriculum`, `CurriculumVersion`, `CurriculumUnit` (is_core, credit_hours, prerequisite) |
| `rooms` | Rooms | `Room`: code (unique), name, building, capacity, room_type, status |
| `timetable` | Timetable | `TimeSlot`, `TimetableSession` (new), plus legacy `AcademicTerm`, `TimetableUploadBatch`, `TimetableSlot`, `TimetableConflict` |
| `uploads` | Excel import pipeline | `TimetableUpload`, `UploadProcessingLog`, `UploadConflictReport` |
| `enrollments` | Student ↔ unit per term | `StudentEnrollment`: student, unit, term, status, score |
| `personalization` | Builds a student's own timetable | services only |
| `analytics` | Metrics | `TimetableMetric` |
| `common` | Base model | `BaseModel`: UUID `id`, `created_at`, `updated_at` |

**`TimetableSession`** (apps/timetable/models/timetable_session.py) — the core output record:
`unit, program, department, lecturer, room, time_slot, academic_year, study_year, semester, day_of_week ("MON".."SUN"), session_type (lecture|practical|tutorial|seminar|workshop|project|field_work), delivery_mode (face_to_face|online|hybrid|blended), student_group, max_students, current_enrollment, status (scheduled|active|completed|cancelled|suspended), created_by, notes`.
Unique together: `(unit, program, study_year, semester, day_of_week, time_slot, student_group, academic_year)`.

**URL map** (config/urls.py)

| Prefix | App |
|---|---|
| `api/v1/auth/token/`, `api/v1/auth/token/refresh/` | SimpleJWT |
| `api/v1/accounts/` | `users/` router; `auth/login/`, `auth/register/`, `auth/profile/`, `auth/profile/update/`, `auth/password/reset/` |
| `api/v1/students/`, `lecturers/`, `departments/`, `programs/`, `units/`, `curriculum/`, `rooms/`, `enrollments/`, `analytics/` | CRUD viewsets |
| `api/v1/personalization/` | `my-timetable/`, `my-units/` |
| `api/v1/timetable/` | `rooms/`, `timeslots/`, `sessions/` (+ `my-timetable`, `lecturer-schedule`, `conflicts` actions), legacy `terms/`, `slots/`, `conflicts/`, `uploads/`, and `upload/` |
| `api/uploads/` (**no `v1`**) | `""` list, `timetable/` create, `validate/`, `reprocess/<uuid>/`, `<uuid>/`, `<uuid>/logs/`, `<uuid>/conflicts/`, `<uuid>/report/` |

**Settings.** `SECRET_KEY` from `DJANGO_SECRET_KEY` (falls back to `"unsafe-dev-secret-key"`), `DEBUG=False` in base, JWT access lifetime 30 min, CORS from env. Development: `DEBUG=True`, `ALLOWED_HOSTS=["*"]`, `CORS_ALLOW_ALL_ORIGINS=True`.

**Excel upload pipeline** (apps/uploads) — `POST /api/uploads/timetable/` runs synchronously inside the request:

1. `ExcelFileValidator` — `.xlsx`/`.xlsm` only, ≤ 25 MB.
2. `ExcelParserService.read_workbook` — reads **sheet 0 only**, `header=0`, then `convert_grid_to_flat` turns the university grid (class rows × day/hour columns, cells `"UNIT\nROOM"`) into one row per session.
3. `ExcelStructureValidator` — 13 required columns.
4. Per row: `TimetableMappingService.build_mapping` (find-or-create department, program, unit, lecturer, room, time slot) → `TimetableDataValidator` → `UploadConflictService` → `UploadProcessingLog`.
5. `TimetableSessionCreationService.bulk_create_sessions` in one transaction.

**Personalization** — `GET /api/v1/personalization/my-timetable/`: resolve student's enrolled units for current year/semester → filter `TimetableSession` by unit, program, study year, semester, academic year → sort and group by day → cache 5 min.

### 3.2 SMARTTT frontend (Flutter) — `SMARTTT_fronted`

- `lib/core/network/api_client.dart` — Dio, base URL `https://api.nextup.co.ke/api/v1/`, 60 s connect / 90 s receive timeouts (Render cold start). Attaches `Bearer` token from SharedPreferences (`auth_token`) except on auth endpoints. On 401, refreshes via `auth/token/refresh/` and retries once.
- `lib/core/router/app_router.dart` — routes: `/`, `/login`, `/register`, `/forgot-password`, `/reset-password`, `/home`, `/lecturer/home`, `/schedule`, `/portal-sync`, `/manual-sync`, `/select-groups`, `/profile`, `/edit-profile`, `/support`, `/student-preferences`, `/terms`, `/privacy`.
- Features: `auth`, `schedule` (timetable view, portal sync, manual sync, group selection, calendar export via `device_calendar`), `lecturer` (home, schedule, notifications, profile tabs), `notifications` (FCM), `profile`, `home`, `alerts`.
- `web/admin.html` — standalone admin page ("SMART ClassCatch Admin") calling the same API.
- `0001-frontend-send-resolved-program-id.patch` — unapplied patch: send `resolved_program_id` from `timetable/metadata/` when saving student preferences.
- **Portal sync** (`portal_sync_screen.dart`): sends the student's university portal username and password to `courses/sync/portal/`; the backend is meant to log in server-side, scrape registered units and discard the credentials.

**Endpoints the app calls**

| Endpoint | Exists in `SMARTTT_BACKEND` repo? |
|---|---|
| `auth/login/`, `auth/register/`, `auth/profile/` (GET/PATCH), `auth/password/reset/` | Under `accounts/` prefix, so path differs — verify against production |
| `auth/password/reset/confirm/`, `auth/lecturer/register/`, `auth/lecturer/profile/`, `auth/account/delete/` | **No** |
| `departments/departments/`, `rooms/rooms/` | Probably (router paths) — verify |
| `timetable/terms/` | Yes |
| `schedule/me/`, `schedule/calendar-token/` | **No** |
| `courses/my-courses/`, `courses/sync/portal/`, `courses/sync/manual/` | **No** |
| `notifications/mine/`, `notifications/unread-count/`, `notifications/{id}/read/`, `notifications/register-token/`, `notifications/lecturer/send/`, `notifications/lecturer/validate-venue/` | **No** |
| `timetable/metadata/` (from the patch) | **No** |

### 3.3 Smart Attendance backend (Node) — `ATTENDANCE_backend`

**Layout.** `src/app.ts`, `src/routes.ts`, `src/config/env.ts` (Zod-validated env), `src/db/` (pg pool + row types), `src/common/` (errors, `{success,data}` response wrapper, utils: campus time, tokens, password, card UID), `src/middleware/` (authenticate, rate limit, validate, request context, error handler), `src/integrations/erp/` and `src/integrations/smarttt/`, `src/modules/<name>/` (`*.routes.ts`, `*.controller.ts`, `*.service.ts`, `*.repository.ts`, `*.schema.ts`). SQL migrations in `db/migrations/` (001–021), run by `npm run db:migrate`.

**Routes** (all under `/api/v1`)

| Module | Routes |
|---|---|
| auth | `POST /auth/lecturer/register`, `/auth/student/register`, `/auth/verify-email`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/change-password`, `/auth/forgot-password`, `/auth/reset-password`; `GET`/`PATCH /auth/me`; `POST`/`DELETE /auth/me/avatar` |
| passkeys | `POST /auth/passkeys/registration/options`, `/registration/verify`, `/authentication/options`, `/authentication/verify` |
| sessions | `POST /sessions`, `GET /sessions/live`, `GET /sessions/:id/qr`, `GET /sessions/:id/qr.image`, `POST /sessions/scan`, `PATCH /sessions/:id/status`, `PATCH /sessions/:id/geofence` |
| attendance | `POST /attendance/check-in`, `/attendance/card-check-in`, `/attendance/fingerprint-check-in`; `GET /attendance/sessions/:id` |
| lecturers | `GET /lecturers/profile`, `/lecturers/overview`, `/lecturers/students` |
| units | `GET /units`, `/units/current`, `/units/:id/students`; `POST /units` |
| students | `GET /students/me/units`, `/students/me/attendance` |
| reports | `GET /reports/sessions`, `/reports/sessions/:id/export` |
| verification (face) | `GET /students/me/face`, `PUT`/`DELETE /students/me/face-consent`, `POST`/`DELETE /units/:unitId/students/:studentUserId/face`, `POST /sessions/:id/face/identify`, `/face/confirm` |
| integrations | `POST /integrations/smarttt/timetable-changes` (X-API-Key) |

**Auth.** Roles `LECTURER`, `STUDENT` only. httpOnly cookies `sa_access` (15 min) and `sa_refresh` (7 d), or `Authorization: Bearer`. Server-side sessions in `auth_sessions`, refresh rotation with reuse detection, 5 failed logins → 15 min lock, per-IP limiter.

**QR check-in** (`src/modules/session/session.token.ts`, `session.service.ts` `verifyScan` ~L433):
payload `v1.<sessionId>.<counter>.<HMAC-SHA256(sessionSecret, "v1.<sessionId>.<counter>")[:16 bytes]>`, `counter = floor(unixSeconds / QR_ROTATION_SECONDS)` (default **45 s**; a comment still says 60). Verification order: shape → session exists → signature/window → session open → QR method enabled → geofence → student allocated to unit → not already checked in → record (DB unique constraint catches races).

**Geofence** (`session.geofence.ts`): haversine distance; accept if `distance − accuracy ≤ radius`. Defaults: `GEOFENCE_RADIUS_METRES=20`, `GEOFENCE_MAX_STUDENT_ACCURACY_METRES=50`, `GEOFENCE_MAX_ANCHOR_ACCURACY_METRES=30`, `GEOFENCE_MAX_FIX_AGE_SECONDS=60`. Room centres surveyed with `npm run dev:set-room`; unsurveyed room → fence around lecturer's device.

**Other check-in methods.** Card (terminal with shared key, `CARD_UID_SECRET`), fingerprint (reader matches; backend only sees a reference, `FINGERPRINT_REF_SECRET`), face (lecturer-held terminal; `face-service` returns 128-d SFace embeddings via OpenCV YuNet + SFace; Node compares).

**SMARTTT client** (`src/integrations/smarttt/`) — see 3.5. Unit sync throttled per lecturer (`SMARTTT_SYNC_INTERVAL_SECONDS=60`), timeout 8 s, no retries, fails soft (shows last synced units).

**`mock-erp/`** stands in for the university ERP (staff and student lookup) on port 4100 with its own DB.

### 3.4 Smart Attendance frontend (React) — `ATTENDANCE_fronted`

- Portals in `src/portals/`: `lecturer/` (dashboard, units + face enrolment, students, attendance: activate class, live session + rotating QR, share location, face terminal, reports, profile), `student/` (dashboard, units, scan QR, face check-in, history, progress, profile), `admin/` (faculties, officers), `faculty/` (overview, departments, lecturers, students, units, officers), `department/` (overview, courses, lecturers, students, units).
- `src/lib/api.ts` unwraps `{success,data}`; on 401 calls `POST /auth/refresh` once.
- `VITE_USE_MOCKS`: `true` all mocked (forbidden in prod), `data` everything real except `GET /lecturer/units`, `false` all real.
- `.env.production`: `VITE_API_URL=/api`, `VITE_SMARTTT_ACCOUNTS=true`. nginx proxies `/api/` to `API_UPSTREAM`.

### 3.5 Integration contracts between them

**Attendance → SMARTTT (pull).** Header `X-API-Key: <SMARTTT_API_KEY>`; must equal `ATTENDANCE_API_KEY` in SMARTTT.

| Path (Attendance env default) | Query | Returns |
|---|---|---|
| `/api/v1/integrations/attendance/lecturer-units/` | `staff_number`, optional `name` | `{ staff_number, lecturer_account, term:{academic_year, semester}, units:[{ code, unit_code, group, name, registered_students, students_without_group, matched_by:"account"\|"name", students:[{registration_number, full_name}], slots:[{day_of_week 0-6 (0=Sunday), start_time "HH:MM", end_time, room, class_group, program}] }] }` |
| `/api/v1/integrations/attendance/students/` | `registration_number` | `{ registration_number, full_name, email, programme, year_of_study, is_active }` |
| `/api/v1/integrations/attendance/staff/` | `staff_number` | staff record |
| `/api/v1/integrations/attendance/student-units/` | `registration_number` | the student's classes this term |

404 → not found; 401/403 → "keys don't match" (logged as error); anything else → unavailable.

**SMARTTT → Attendance (push).** When a slot is rescheduled (`POST /api/v1/timetable/slots/{id}/reschedule/` in SMARTTT), SMARTTT sends `POST {ATTENDANCE_BASE_URL}/api/v1/integrations/smarttt/timetable-changes` with `X-API-Key` and `{ "staff_number": "STF/0001", "unit_codes": ["COSC 103 GR A"] }`. Attendance re-syncs those lecturers immediately and answers `{ "lecturersResynced": n }`. Best effort; never blocks the reschedule.

**Neither `apps/integrations` nor the reschedule endpoint exists in the `SMARTTT_BACKEND` GitHub repo.** They must exist in production (see 4.1).

---

## 4. Known problems, by severity

### 4.1 Critical — fix before anything else

| # | Problem | Where | Fix |
|---|---|---|---|
| C1 | **GitHub repos are behind production.** SMARTTT is missing `apps/integrations`, the reschedule endpoint, and every Flutter endpoint marked "No" in 3.2. Attendance backend is missing everything the React admin/faculty/department portals call (C2). | Both backends | Push the code that runs on `api.nextup.co.ke` / Render to GitHub. Do not rebuild these from scratch until confirmed they are truly missing. |
| C2 | Attendance frontend calls endpoints the backend doesn't have: `/admin/*`, `/faculties/*`, `/departments/*`, `/auth/invitations/lookup`, `/auth/invitations/accept`, `/face/warm-up`, `/lecturer/units`. Backend roles are only `LECTURER`/`STUDENT`. `.env.production` mentions backend setting `SMARTTT_ACCOUNTS`, which doesn't exist. | `ATTENDANCE_fronted` vs `ATTENDANCE_backend` | Confirm whether this backend code exists unpushed (C1); otherwise implement (task T0.4). |
| C3 | **Secrets committed.** `.env`, `db.sqlite3`, `server.log` and real uploaded timetables under `media/` are tracked in git, although `.gitignore` lists them. | `SMARTTT_BACKEND` | `git rm --cached` them, rotate `DJANGO_SECRET_KEY` and the Postgres password, consider history rewrite. |
| C4 | **Every uploaded session gets lecturer "Staff".** Empty lecturer → `"Staff"` and a fake user `staff@example.com`. | `apps/uploads/services/timetable_mapping_service.py` L109–149 | Leave lecturer null (the model allows it). The new Allocator supplies lecturers. |
| C5 | **Every programme goes under "School of Computing".** Empty department → default. New programmes get `description="Bachelor of Science in {value}"`, `duration_years=4`. | same file L17–56 | Use the department/program chosen on the upload form; never invent descriptions. |
| C6 | **After the first upload, later uploads lose most rows.** Because every session has lecturer "Staff", the lecturer-clash check flags almost every row of any later upload for the same term. | `upload_conflict_service.py` + C4 | Fixed by C4. |

### 4.2 High

| # | Problem | Where |
|---|---|---|
| H1 | Conflicts are only checked against the DB, never within the uploaded file (rows are saved at the end). The May–Aug 2026 file has **216 room-hours with two different units in one room**, none flagged. | `upload_conflict_service.py`, `upload_processing_service.py` |
| H2 | Year/semester detection misses the title. `read_excel(header=0)` turns the title row ("…MAY-AUGUST 2026…") into column names, so the "may-august" check never sees it; 578 of 902 sessions saved as semester 1. Academic year defaults to hard-coded `"2025/2026"`, and "2026/2027" becomes "2025/2026". | `excel_parser_service.py` L13, L150–164; mapping L93 |
| H3 | Header time parsing reads hours only: `"8:30-9:30"` breaks; 12-hour `"1-2"` becomes 01:00–02:00. Case B detection (`^\d+[-:]\d+$`, L98) disagrees with its parser (L134). | `excel_parser_service.py` L40–90, L98, L134 |
| H4 | Students without enrollments get an empty timetable: both branches return `source="enrollment"`; curriculum fallback is missing. | `apps/personalization/services/student_unit_resolution_service.py` |
| H5 | Semester validator only allows `{1, 2}`; May–August is **semester 3** (decided). | `apps/uploads/validators/timetable_data_validator.py` L32–34 |
| H6 | Password reset is a stub that returns "email sent". | `apps/accounts/views/auth_views.py` `PasswordResetView` |
| H7 | Upload has no `try/except`; a failure leaves status stuck at `validating`/`processing`. | `upload_processing_service.py` |
| H8 | Upload runs ~10–15 queries per row synchronously (~10k queries for 900 rows) — timeouts on Render. | upload pipeline |

### 4.3 Medium / cleanup

- Duplicate code paths: two `StudentEnrollment` models (`students` and `enrollments`), legacy timetable models alongside new ones, two Excel pipelines (`apps/timetable/services/*` and `apps/uploads/services/*`).
- `excel_parser_service.py` L166–209 is a dead duplicate of L118–148.
- `parse_rows` `row_number = index + 2` is meaningless after grid flattening; error reports point to wrong rows.
- Upload auto-creates `Curriculum`/`CurriculumUnit` (mapping L88–105) — an upload should not change curriculum.
- Rooms auto-created with `capacity=100`; `max_students` copied from that.
- Cohorts without `Y<n>` (e.g. "BED ENG/LITT") default to study year 1.
- `reprocess_upload` re-runs everything; existing rows are all skipped as duplicates.
- Attendance: geofence effectively accepts up to ~70 m (20 m radius + 50 m accuracy); `isMocked` is client-reported. README says "no migrations / only lecturer registration implemented" — both stale. Migration numbers 012 and 019 are reused.
- Attendance `day_of_week` is 0–6 (Sunday=0); SMARTTT stores `"MON".."SUN"`. One conversion point, with a test.

---

## 5. New systems: Timetable Generator and Timetable Allocator

### 5.1 Purpose and scope

Replace the hand-made teaching timetable (today a 62-page PDF from the Directorate of Examinations and Timetabling) and the per-department Word allocation forms with **two new systems in two repos**:

- **Timetable Generator** (`Kim-254-de/Timetable-Generator`) — Director of Examinations and Timetabling: sets up groups, runs the solver, reviews, approves, publishes.
- **Timetable Allocator** (`Kim-254-de/Timetable-Allocator`) — each department's Chair of Department: assigns a lecturer to each group of the units the department owns, **after** the timetable is published.

**How the two repos relate**

| | Timetable Generator | Timetable Allocator |
|---|---|---|
| Users | Director of Exams and staff | CODs and department staff |
| Reads from SMARTTT | Master-data snapshot (5.4), incl. currently allocated lecturers for repair re-solves | Published sessions, lecturers, each lecturer's other sessions |
| Writes to SMARTTT | A published timetable version | The lecturer on a published session |
| Owns (its own DB) | Terms, class rows, offerings, groups, runs, drafts, publications | Allocations, lecturer availability, submissions |
| Needs a solver | Yes (OR-Tools CP-SAT + worker) | No |
| Talks to the other repo | **Never** — only through SMARTTT | **Never** — only through SMARTTT |

**Layout of each repo** (same in both)

```
<repo>/
  backend/            FastAPI app: app/api, app/models, app/services, app/clients/smarttt.py, alembic/, tests/
  frontend/           React 19 + Vite + TanStack Query + Tailwind (match ATTENDANCE_fronted conventions)
  docker-compose.yml  postgres (+ redis and worker in Generator)
  .env.example        SMARTTT_BASE_URL, SMARTTT_API_KEY, DATABASE_URL, …
  README.md
  SYSTEM_HANDOFF.md   this file
```

Each repo has its **own** `SMARTTT_API_KEY`, so SMARTTT can tell which system is calling and limit each to its own endpoints (5.10).

**In scope (v1):** teaching timetable for one term; group splitting; solver; manual edits with live validation; publish to SMARTTT; lecturer allocation with live clash checks; PDF exports in today's layouts; repair re-solve for mid-term changes.
**Out of scope (v1):** exam timetabling; per-student elective scheduling; replacing SMARTTT's apps.

### 5.2 Worked examples (from the client)

Unit not split:

| Generator output | Allocator output |
|---|---|
| COSC 100 · UTC 1 · MON 10:00–11:00 | COSC 100 · Dr. Jane |

Large unit split into groups (each group = its own class, room, lecturer):

| Generator output | Allocator output |
|---|---|
| COSC 103 GR A · STB 1 · TUE 10:00–12:00 | COSC 103 GR A · Dr. Jane |
| COSC 103 GR B · STB 2 · TUE 10:00–12:00 | COSC 103 GR B · Dr. Collins |
| COSC 103 GR C · STB 3 · TUE 10:00–12:00 | COSC 103 GR C · Dr. John |

The two halves join on the **class key** (`COSC 103 GR A`).

### 5.3 Domain model

| Concept | Meaning |
|---|---|
| **Class row** | A cohort as printed on the timetable: programme + year + semester, optionally a sub-class number. Examples: `B.LAW Y1S1`, `BSC.NURSING Y2S1`, `BED.BIO/AGR Y1S1 (3)`. ~380 rows in Sep–Dec 2026. |
| **Unit offering** | A unit taught this term (e.g. COSC 103), owned by one department, with `weekly_hours` and `session_length`. |
| **Group** | One class of an offering: label (`GR A`, `GR T2`…), the class rows it serves, student count. An unsplit unit has exactly one group. A group can mix programmes, e.g. *Group K: MATH/CHEM, AGRI/CHEM (150)*. |
| **Servicing** | The department that **owns** the unit allocates the lecturer even when students belong to another department (e.g. Computer Science teaches COSC 103 to Education). |
| **Session** | One timetabled meeting of a group: room, day, start, end. Stable `key` across versions. |
| **Allocation** | Group → lecturer (+ full-time / part-time). Phone numbers live on the lecturer profile, not the allocation. |

### 5.4 Data the service needs from SMARTTT (snapshot)

| Input | SMARTTT source | Gap to close in SMARTTT |
|---|---|---|
| Term, teaching week | `AcademicTerm`, `TimeSlot` | Allow semester 3 |
| Class rows | `Program`, `Student.current_study_year` | De-duplicate programmes; put each under its real department; add sub-class rows |
| Units per class row | `Curriculum`, `CurriculumUnit` | Stop the Excel upload from auto-creating curricula |
| Class sizes | count of students per class row | — |
| Rooms | `Room` (code, building, capacity, room_type, status) | Survey real capacities (~90 rooms: TC, STB, ASB, ED, BS, UTC, UTC-AA..AE, G 1–30) |
| Lecturers per department | `Lecturer` + `max_weekly_teaching_hours` | Add `employment_type` (FT/PT) |

New data, owned by the two new repos: **Timetable-Generator** owns class rows, unit offerings, groups, runs, drafts and publications; **Timetable-Allocator** owns allocations, lecturer availability and submissions (5.8).

### 5.5 Constraints

**Hard (never broken)**

| # | Rule | Enforced by |
|---|---|---|
| H1 | A room hosts at most one session per hour (a group serving several class rows = one session) | Generator |
| H2 | A class row attends at most one session per hour, across every group it belongs to | Generator |
| H3 | Room capacity ≥ group's student count | Generator |
| H4 | Room type matches session (lecture hall, lab, studio) | Generator |
| H5 | Every session of every group scheduled exactly once, full length | Generator |
| H6 | Multi-hour sessions use consecutive hours, same day, same room | Generator |
| H7 | Only Monday–Friday, 07:00–19:00 (60 one-hour slots). No Saturday/evening; no common hour | Generator |
| H8 | No session when its room or class row is marked unavailable | Generator |
| H9 | **Department capacity:** in any hour, a department's running classes ≤ its number of lecturers (FT + PT) | Generator |
| H10 | Pinned sessions keep slot and room | Generator |
| H11 | A lecturer teaches at most one session per hour | Allocator |
| H12 | A lecturer is not allocated when unavailable or beyond `max_weekly_teaching_hours` | Allocator |
| H13 | **Repair re-solves only:** a session that already has a lecturer cannot be moved onto an hour where that lecturer teaches something else | Generator (reads allocated lecturers from the SMARTTT snapshot) |

**Soft (weighted penalties, tunable per run)**

| # | Preference | Default weight |
|---|---|---|
| S1 | Avoid one-hour gaps in a class row's day | High |
| S2 | Spread a unit's sessions over different days | High |
| S3 | ≤ 5 teaching hours per class row per day | Medium |
| S4 | Avoid 07:00 and after 17:00 where possible | Medium |
| S5 | Department's classes spread across the week (eases allocation) | Low |
| S6 | Same building for a class row on the same day | Low |
| S7 | Room size close to class size | Low |
| S8 | On re-solve, keep sessions where they were | Very high (re-solve only) |

Context: in May–Aug 2026, 302 of 902 sessions started at 07:00 and only 8 at 15:00 or later.

### 5.6 Solver design (OR-Tools CP-SAT, two phases)

Solving time × room together ≈ 902 sessions × 60 hours × 39 rooms ≈ 2.1 M booleans. Split:

**Phase 1 — time.**
1. Each session → `NewIntervalVar` with fixed length; start domain = allowed hours on one day (H6, H7, H8).
2. `AddNoOverlap` over each class row's intervals (H2).
3. For each room type and each capacity threshold *t*: in every hour, `#sessions needing ≥ t` ≤ `#rooms with capacity ≥ t` (nested Hall condition ⇒ phase 2 always finds rooms) (H1, H3, H4).
4. Per department, per hour: running sessions ≤ lecturer count (H9).
5. Pinned sessions fixed (H10). Soft constraints as weighted penalty terms; minimise sum.

**Phase 2 — rooms.** With times fixed, each session picks one of its suitable rooms (~5–10 candidates; ~7k booleans); no two time-overlapping sessions share a room; multi-hour sessions keep one room. Objective from S6, S7. Solves in seconds.

**Performance.** Target < 10 min for the whole university with a user-set time limit (return best found). Use multiple workers, hint from last term, pool identical rooms. Per-school decomposition as fallback.

**Infeasibility.** Pre-checks first (capacity per room type/size, department load vs lecturers, class-row hours vs 60). Then CP-SAT assumptions to name the failing rule and the entity (illustrative message: "BED.BIO/AGR Y1S1 (3) needs N lab-hours; only M are free").

### 5.7 Workflow and states

States: `draft` → `published` → `allocated` (per group). Every publish = numbered version, can be rolled back.

1. **Open term (Director).** Confirm rooms; offerings from curricula. Generator proposes group splits from student numbers and largest suitable rooms; **the Director decides the final split.**
2. **Generate (Director).** Start a run (weights, time limit) in a background worker; keep several drafts.
3. **Review (Director).** Grids per class row and per room (like today's PDF) with soft-constraint scores. Drag-and-drop moves validated live against hard rules.
4. **Pin and re-solve.** Moved sessions pinned; re-solve the rest.
5. **Approve and publish (Director).** **Only the Director approves**; no other sign-off. Students see room/time with lecturer "to be allocated".
6. **Allocate (departments).** Each COD sees their groups with slots (incl. servicing) and picks from lecturers **free at that hour**. Each allocation is sent to SMARTTT on save. Director sees outstanding departments.
7. **Mid-term change.** Edit inputs, run a **repair re-solve** (S8 keeps unaffected sessions), publish new version; only changed sessions propagate. If no lecturer is free for a group, the COD asks the Director to move just that group.

### 5.8 Data models (one database per repo)

**`Timetable-Generator` database**

| Table | Columns (indicative) |
|---|---|
| `terms` | id, smarttt_term_id, academic_year, semester (1–3), status |
| `snapshots` | id, term_id, json, sha256, created_at |
| `class_rows` | id, term_id, smarttt_program_id, study_year, study_semester, sub_class, label, student_count |
| `unit_offerings` | id, term_id, smarttt_unit_id, owning_department_id, weekly_hours, session_length, room_type |
| `groups` | id, offering_id, label, student_count; `group_class_rows(group_id, class_row_id)` |
| `runs` | id, term_id, snapshot_id, mode (full\|repair), weights json, time_limit_s, status, score, solve_seconds, failure json |
| `drafts` | id, run_id, parent_draft_id, status |
| `draft_sessions` | key, draft_id, group_id, smarttt_room_id, day, start, end, pinned |
| `publications` | version, term_id, draft_id, published_by, published_at, smarttt_response json |
| `audit_log` | id, actor, action, entity, before json, after json, at |

**`Timetable-Allocator` database**

| Table | Columns (indicative) |
|---|---|
| `terms` | id, smarttt_term_id, published_version_seen |
| `allocations` | id, term_id, session_key, group_label, smarttt_unit_id, smarttt_lecturer_id, employment_type, entered_by, entered_at, synced_to_smarttt_at, status (draft\|saved\|submitted) |
| `lecturer_availability` | id, term_id, smarttt_lecturer_id, day, start, end, reason |
| `submissions` | id, term_id, department_id, submitted_by (COD), submitted_at |
| `audit_log` | id, actor, action, entity, before json, after json, at |

The Allocator keeps no copy of the timetable: it reads published sessions from SMARTTT each time (cache ≤ 60 s) and treats SMARTTT as the truth for "who teaches what, when".

### 5.9 APIs of the two repos

**`Timetable-Generator` API**

| Method + path | Does |
|---|---|
| `POST /terms/{id}/snapshots` | Pull snapshot from SMARTTT; report missing data |
| `POST /terms/{id}/groups/propose`, `PATCH /groups/{id}` | Propose / edit group splits (Director decides) |
| `POST /runs`, `GET /runs/{id}` | Start a run (full or repair); progress, best score, failure explanation |
| `GET /drafts/{id}?view=row\|room\|department` | Grid view |
| `PATCH /drafts/{id}/sessions/{key}` | Move/pin; 409 if a hard rule breaks |
| `POST /drafts/{id}/resolve` | Re-solve around pins |
| `POST /drafts/{id}/publish` | Director approves + pushes to SMARTTT |
| `GET /drafts/{id}/export.pdf` | Today's teaching-timetable PDF layout |

**`Timetable-Allocator` API**

| Method + path | Does |
|---|---|
| `GET /departments/{id}/sessions?term=` | The department's published groups and slots to allocate, incl. servicing |
| `GET /sessions/{key}/free-lecturers` | Lecturers free at that slot, available, within weekly hours |
| `PUT /sessions/{key}/allocation` | Set lecturer; re-checks clash against SMARTTT, then PATCHes SMARTTT; 409 on clash (H11, H12) |
| `PUT /lecturers/{id}/availability` | Lecturer unavailability for the term |
| `POST /departments/{id}/submit` | COD submits the department's allocation |
| `GET /departments/{id}/progress` | Allocated vs outstanding (also shown to the Director) |
| `GET /departments/{id}/allocations/export.pdf` | Today's allocation-form layout: Course code, Course title, L, P, CF, Lecturer |

**Clash check (H11) must be race-safe.** Two departments can try to give the same part-time lecturer two classes at the same hour. The final check happens **in SMARTTT** inside the lecturer PATCH (row lock on the lecturer's sessions for that term); the Allocator's own check is only for fast feedback.

**Access.** Both sign in with SMARTTT accounts (SMARTTT issues the JWT; each repo verifies it). Generator: Director's office only. Allocator: department staff see only their department; only the COD can submit; the Director can view progress for all departments.

### 5.10 New SMARTTT endpoints (in `apps/integrations`, `X-API-Key`)

Two keys: `GENERATOR_API_KEY` (Generator endpoints only) and `ALLOCATOR_API_KEY` (Allocator endpoints only).

**As built** (`apps/integrations/timetabling_views.py`; `term` defaults to the current term everywhere):

| Endpoint | Called by | Purpose |
|---|---|---|
| `POST …/allocator/authenticate/`, `POST …/generator/authenticate/` | both | SMARTTT login check → account, `timetabling_office`, `departments[{id, code, name, role: cod\|admin\|editor}]`; wrong password = 200 `{authenticated: false}` |
| `GET …/allocator/identity/?account_id=`, `GET …/generator/identity/?account_id=` | both | Same identity without a password, for refreshing sessions; 404 when inactive |
| `GET …/allocator/terms/`, `GET …/generator/terms/` | both | Academic terms |
| `GET /api/v1/integrations/generator/snapshot/?term=<id>` | Generator | Rooms, departments with FT/PT lecturer counts, lecturers, programmes, units, curricula, class sizes, registrations, `published.{version, sessions[key, unit_id, group_label, section_key, room_id, day, start, end, class_rows, lecturer_id]}`, `warnings` |
| `POST /api/v1/integrations/generator/publish/` | Generator | Publish a version (body below). 201 new, 200 same version re-sent, 409 `stale_base`/`version_taken`/`unpublished_slots`/`lecturer_clash`, 422 rule violations |
| `GET /api/v1/integrations/generator/publish/<version>/?term=<id>` | Generator | Publish status |
| `GET /api/v1/integrations/allocator/departments/` | Allocator | Active departments with their COD, for the Director's progress view |
| `GET /api/v1/integrations/allocator/sections/?term=<id>&department=<id>` | Allocator | Published sections (unit + group) whose unit the department owns: key, code, unit, group, class rows (with programme department, for servicing), meetings, weekly hours, registered students, current lecturer |
| `GET /api/v1/integrations/allocator/sections/<key>/?term=<id>` | Allocator | One section |
| `GET /api/v1/integrations/allocator/lecturers/?department=<id>&term=<id>` | Allocator | Lecturers with employment type and `max_weekly_teaching_hours`; with `term`, each lecturer's meetings and weekly hours (one call for "who is free") |
| `GET /api/v1/integrations/allocator/lecturers/<id>/sessions/?term=<id>` | Allocator | Everything a lecturer already teaches this term, across all departments |
| `PATCH /api/v1/integrations/allocator/sections/<key>/lecturer/?term=<id>` | Allocator | `{lecturer_id \| null, expected_lecturer_id}` sets/clears the lecturer on every slot of the section. Row lock on the lecturer; 409 `lecturer_clash`/`max_hours`/`stale`; pushes the change to Attendance |

Session-level rows in SMARTTT are `TimetableSlot` (one per class row per meeting), keyed by the Generator's stable `session_key`; a section is all slots with the same unit and group.

```json
{
  "term_id": "9b2f…",
  "version": 4,
  "based_on_version": 3,
  "sessions": [
    {
      "key": "COSC103-GRA-1",
      "unit_id": "…", "group_label": "GR A",
      "class_rows": [{"program_id": 10, "year_of_study": 1, "study_semester": 1, "stream": ""}],
      "room_id": "…",
      "day_of_week": "TUE", "start_time": "10:00", "end_time": "12:00"
    }
  ],
  "published_by": "<account id and name>",
  "replace_unpublished": false
}
```

(As built: class rows are sent as programme/year/semester/stream because SMARTTT has no class-row table; lecturers are not part of the payload — SMARTTT keeps each section's lecturer; `session_type` was dropped because `TimetableSlot` has no such field.)

Rules: validate whole version then write in **one transaction**; **idempotent** on `(term_id, version)`; update by stable `key` (keeps Attendance records linked); refuse if current version ≠ `based_on_version`. After publish or lecturer change, compute changed sessions and send the existing Attendance push (3.5). Attendance can only activate a class once it has a lecturer.

---

## 6. Business rules already decided

| Rule | Decided by |
|---|---|
| Director of Examinations and Timetabling runs the Generator | Client |
| Departments (COD) run the Allocator | Client |
| **Director decides how a unit is split into groups** | Client |
| **Director approves the timetable before publishing; no other sign-off** | Client |
| **Departments allocate lecturers after the timetable is published** | Client |
| **Teaching only Monday–Friday, 07:00–19:00**; no Saturday or evening classes | Client |
| **No fixed common hour** | Client |
| **Three semesters a year; May–August = semester 3** | Client |
| Handoff to SMARTTT by direct API push, not Excel | Team |
| Solver stack: Python + OR-Tools CP-SAT | Team |
| Master data source: SMARTTT database | Team |

---

## 7. Work plan for Claude Code

Work in order. Each task is a separate branch and PR. Do not start a phase until the previous phase's checks pass.

### Phase 0 — Foundation (SMARTTT + Attendance)

- **T0.1 Sync repos with production.** Ask the team for the production code of SMARTTT and Attendance backend; push it. *Done when:* `apps/integrations` exists in SMARTTT and every endpoint listed in 3.2 / C2 is either present or explicitly confirmed missing.
- **T0.2 Remove secrets.** `git rm --cached .env db.sqlite3 server.log media/`; keep `.env.example`; document rotation. *Done when:* `git ls-files` shows none of them; settings refuse to start in production without `DJANGO_SECRET_KEY`.
- **T0.3 Fix upload pipeline data damage** (C4, C5, H1, H2, H3, H5, H7). Null lecturer, use form's department/program, in-file conflict detection with a seen-set, read title with `header=None`, minute + 12-hour time parsing, semester ∈ {1,2,3}, `try/except` → `failed`. Delete L166–209 duplicate. Stop curriculum auto-creation. *Done when:* tests in `apps/uploads/tests/` cover each bug using `media/.../TUN_MAY_AUG_2026_Timetable-2.xlsx`; that file yields 902 sessions, the term recorded as May–August (semester 3), academic year from the title, conflicts reported. Keep the class row's own study semester (the "S1" in "Y2S1") separate from the term — see open question 3.
- **T0.4 Fill missing endpoints** only if T0.1 confirms they are missing (Flutter `schedule/*`, `courses/*`, `notifications/*`, lecturer register; Attendance admin/faculty/department/invitations).
- **T0.5 Data clean-up.** De-duplicate programmes, map to departments, add sub-class rows, `Lecturer.employment_type`, room capacity import. *Done when:* management command reports zero programmes under the default department.
- **T0.6 Personalization fallback** (H4) and real password reset (H6).

### Phase 1 — `Timetable-Allocator` repo

The Allocator is built first: it needs no solver, and it can be tested on the timetable already in SMARTTT (imported with the T0.3 fixes) before the Generator exists.

- **T1.1** Scaffold `Kim-254-de/Timetable-Allocator` with the layout in 5.1: FastAPI, SQLAlchemy + Alembic, PostgreSQL, pytest, ruff, mypy; React 19 + Vite frontend; docker-compose; `.env.example`; README; copy this file in.
- **T1.2** In SMARTTT: the four `allocator/*` endpoints in 5.10, with `ALLOCATOR_API_KEY` and the locked clash re-check in the lecturer PATCH.
- **T1.3** In the Allocator: SMARTTT client (`app/clients/smarttt.py`), models and migrations per 5.8 (Allocator tables), SMARTTT JWT verification.
- **T1.4** Allocator API per 5.9 with H11/H12 checks, `free-lecturers`, submit, progress.
- **T1.5** Allocator web UI: department view of groups and slots, pick from free lecturers, availability, submit, progress, PDF export.
- *Phase check:* Computer Science enters its Sep–Dec 2026 allocation (source: `VETTED_SEP-DEC ALLOCATION 2026.docx`, ~240 unit rows, 107 lecturers, 7 servicing sections); every lecturer appears in SMARTTT on the right sessions; a deliberate double-booking is refused; the PDF has the Word form's columns (Course code, Course title, L, P, CF, Lecturer).

### Phase 2 — `Timetable-Generator` repo: solver

- **T2.1** Scaffold `Kim-254-de/Timetable-Generator` with the layout in 5.1, plus Redis + RQ worker and `ortools`.
- **T2.2** In SMARTTT: `generator/snapshot/` with `GENERATOR_API_KEY`. In the Generator: SMARTTT client, snapshot storage with hash, models and migrations per 5.8 (Generator tables).
- **T2.3** Group proposal algorithm (split by student count vs largest suitable room; the Director edits and decides).
- **T2.4** CP-SAT phase 1 + phase 2 per 5.6; pre-checks; infeasibility explanations.
- **T2.5** Benchmark fixture: rebuild Sep–Dec 2026 inputs from `TUN SEP-DEC 2026 TEACHING TT V2.pdf` (pdftotext works; ~380 class rows, ~700 unit codes, ~90 rooms).
- *Phase check:* zero hard violations; < 10 min; fewer gaps and fewer 07:00/late sessions than the hand-made timetable; report printed per soft constraint.

### Phase 3 — `Timetable-Generator` repo: Director's web UI

- **T3.1** Background runs with progress; drafts; grid views (class row, room, department) styled like the PDF; drag-and-drop with live validation; pin; re-solve.
- **T3.2** PDF export in today's layout (Directorate header, Mon–Fri × 7–19 grid, "UNIT / GR X / ROOM" cells, "Prepared by … Director Examination & Timetabling" footer).
- *Phase check:* the Director's office builds one school's timetable end to end unaided.

### Phase 4 — Publish and integrate (SMARTTT + both repos + Attendance)

- **T4.1** SMARTTT `generator/publish/` (5.10) with transaction, idempotency, stable keys, version guard. Generator `POST /drafts/{id}/publish` calls it.
- **T4.2** SMARTTT → Attendance push on publish and on every Allocator lecturer change; `lecturer-units` reads published sessions + lecturer; day-of-week conversion test.
- **T4.3** Repair re-solve in the Generator, honouring H13 (allocated lecturers stay clash-free). After a repair publish, the Allocator shows any session whose lecturer was cleared or now clashes.
- *Phase check:* a mid-term room change reaches the lecturer's Attendance "Activate class" card within one minute.

---

## 8. Open questions

Ask the team; do not assume.

1. **Weekly hours.** How do the allocation form's L, P and CF hours map to weekly timetable hours? Most units meet once a week for 2 hours, yet many forms list 30 lecture + 30 practical hours per semester.
2. **Practical rooms.** Do practicals need specific named labs, or any room of the right type?
3. **Term vs study semester.** Class rows carry their own study semester ("BSC.NURSING Y2**S1**") while the calendar term is semester 1, 2 or 3 (May–August = 3). SMARTTT currently stores one `semester` field for both. Confirm the two should be stored separately (proposed: `term.semester` and `class_row.study_semester`).

---

## 9. Conventions and guardrails

- **Never** commit `.env`, databases, logs, uploaded files or personal data (phone numbers, student lists).
- **Which repo?** Timetable building, groups, solver, Director UI → `Timetable-Generator`. Lecturer allocation, availability, COD UI → `Timetable-Allocator`. Master data, published timetable, the integration endpoints both new repos call → `SMARTTT_BACKEND`. A task that changes an API contract updates both sides in the same piece of work, and this file.
- The two new repos must not import each other's code or call each other's API. Shared contract = the SMARTTT endpoints in 5.10.
- Shared-key auth between services: header `X-API-Key`, compared in constant time; fail closed when unset.
- Keep each repo's existing style: Django apps with `services/ selectors/ validators/` in SMARTTT; `*.routes/controller/service/repository/schema.ts` in Attendance; Zod/Pydantic validation at the edge.
- Every behaviour change ships with tests. Use the real sample files (section 10) as fixtures.
- Times are campus time (Africa/Nairobi, UTC+3). Days: store `MON..FRI` in SMARTTT; convert at the Attendance boundary.
- No silent defaults that invent data (no "Staff", no "School of Computing", no hard-coded academic year).
- Publishing and allocation must be idempotent and auditable.

---

## 10. Reference data

| File | What it shows |
|---|---|
| `SMARTTT_BACKEND/media/uploads/timetables/2026/05/27/TUN_MAY_AUG_2026_Timetable-2.xlsx` | May–Aug 2026 timetable. Sheet "Full Timetable" + 63 per-class sheets. Header row 3: `Mon\n7-8` … `Fri\n18-19` (60 columns). 63 class rows, 902 sessions, 39 rooms, 392 units (363 meet 2 h/week), 37 units taken by >1 class row. |
| `TUN SEP-DEC 2026 TEACHING TT V2.pdf` (client) | 62-page Sep–Dec 2026 teaching timetable, version dated 19/09/2026, in use from 21/09/2026. ~380 class rows; cells "UNIT / GR X / ROOM"; mostly 2-hour blocks; prepared by the Director Examination & Timetabling. |
| `VETTED_SEP-DEC ALLOCATION 2026.docx` (client) | Department of Computer Science and ICT allocation, dated 1/7/26, prepared by the COD. One table per class row ("YEAR 1 SEMESTER 2 (5 Students)"), columns Course code, Course title, L, P, CF, Lecturer (FT/PT), Phone. Includes groups ("Group K: MATH/CHEM, AGRI/CHEM (150)") and 7 "servicing for other departments" sections. |
| Design doc (Claude Docs) | "Timetable Generator — System Design". Written before the split into two repos; **where it differs, this file wins.** |
