# UI redesign, November 2026

The Generator's look was redesigned on `main` by Kim (commit `92b6e80`, 13 Nov 2026,
"Redesign the Generator in SMARTTT's look; add the Director's profile"): royal blue
sidebar, white top bar, SMARTTT's font, Home dashboard, Term page as Teaching / Exams
step flows, Lecture halls grouped by building, side panels, Director profile.

A parallel redesign of Lecture halls and the Term page on `wayler` (12 Nov) was
**dropped in favour of Kim's** when `main` was merged into `wayler` (`0aaf748`). These
small additions from it were kept, on top of Kim's screens:

| Where | Addition |
|---|---|
| Sign-in page (`App.tsx` `LoginPage`) | The theme switch, top right, as in the top bar |
| Lecture halls (`pages/RoomsPage.tsx`) | Exam seats show the real number at the default spacing, e.g. **180 auto** for a 200-seat hall (capacity × 0.9), instead of "× spacing". A fixed number still shows as set |
| Lecture halls | Deleting a hall asks inside the row ("Delete TC 1? Used by N classes. Delete · Keep") instead of the browser's pop-up |

Smart Attendance's Teaching page and the SMARTTT Class Schedule changes are documented
in `ATTENDANCE_fronted/docs/ui-redesign-2026-11.md` and
`SMARTTT_fronted/docs/ui-redesign-2026-11.md`.
