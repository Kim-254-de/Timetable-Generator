# UI redesign, November 2026

A page-by-page pass to make the Timetable Generator and Smart Attendance look
and read as one platform. The rules follow Smart Attendance's
`docs/portal-layout-review.md` (§6 covers the Generator); colours and fonts were
already shared, so this pass is about **layout, wording and removing clutter**.
No API or data changes.

The Attendance pages are in `ATTENDANCE_fronted/docs/ui-redesign-2026-11.md`.

## Shared parts added

- `frontend/src/components/ui/Button.tsx`: the same button as Smart Attendance's
  (primary, secondary, ghost, danger; rounded, 44 px tall, optional loading spinner).
- `frontend/src/components/ui/Card.tsx`: the same card (rounded, soft shadow, no border).

Use these on every page from now on instead of hand-styled `rounded-md` buttons,
so the Generator's 8 different button styles come down to 4.

## Lecture halls (`/rooms`, 12 Nov 2026)

The Director's list of rooms the solver may use, shared by every term.

| Before | After |
|---|---|
| Square buttons, bordered table | Attendance's **Button** and **Card**: rounded buttons, table in a soft-shadow card, larger search box |
| Three buttons: *Bring in from SMARTTT*, *Paste from Excel*, *+ Add a lecture hall* | One **Import ▾** menu (SMARTTT or Excel, each with a one-line note) next to **+ Add a lecture hall** |
| "6 rooms · 470 seats available. Used by every term." | "5 open · 1 closed · 470 seats · shared by every term" |
| *Available* column: "Yes" / "Closed" in plain text | **Status** column with **Open** (green) / **Closed** (grey) badges; closed rooms listed last |
| Exam seats: "× spacing" | The real number at the default spacing, e.g. **180 auto** (capacity 200 × 0.9); a fixed number still shows as set |
| Red *Delete* on every row, with the browser's pop-up | Rows show only **Edit**. *Delete this room* is inside the Edit dialog, with an in-app confirmation ("Delete TC 1? This can't be undone." · Keep it / Delete), and it says how many saved classes use the room |
| Error and SMARTTT messages as plain text | Coloured message boxes (red for errors, green for the SMARTTT result) |

"auto" seats use the default spacing 0.9; a term whose exam period sets another
spacing uses that when generating, as before. The page only displays the number.

Files: `frontend/src/pages/RoomsPage.tsx`, `frontend/src/components/ui/Button.tsx`, `frontend/src/components/ui/Card.tsx`.

## Term page (`/terms/:id`, 12 Nov 2026)

The Director's workspace for one term: details, departments' imports, class rows,
units, generating, timetables and exams.

| Before | After |
|---|---|
| Top bar highlighted **Home** on every term page | Highlights **Terms** (layout review §6) |
| Seven plain underline tabs, teaching and exams mixed | Two labelled sections, as on Attendance's Teaching page: **Teaching timetable** with numbered steps (1 Term details, 2 Departments, 3 Class rows, 4 Units and groups, 5 Generate, 6 Timetables and downloads) and **Exams** |
| "What the Generator needs" list repeating the tabs | Removed; a small **Shared lists** card links the lecture halls and departments counts, and keeps *Start from a previous term* |
| "Ready to generate?" at the bottom of Term details; "1 things to fix first" | A status strip at the **top** of Term details: green "Ready to generate" or amber "Not ready to generate: 1 thing to fix first" with the list |
| Departments tab: two-sentence explanation and a footnote line about late imports | One line: "What departments published from their Teaching page in Smart Attendance."; the late-import advice is a collapsible **ⓘ A department published after you did?** tip |
| Square buttons, bordered panels, small inputs on every tab | Attendance look on every tab: rounded 44 px buttons (36 px inside tables), soft-shadow cards, rounded inputs. `components/Dialog.tsx` `inputClass` updated, so every form in the Generator gets the rounded inputs |

Files: `frontend/src/App.tsx`, `pages/TermPage.tsx`, `pages/TermEntry.tsx`,
`components/DepartmentSubmissions.tsx`, `components/ExamsTab.tsx`, `components/ExamSwitch.tsx`,
`components/DirectorPapers.tsx`, `components/Dialog.tsx`.


## Theme button everywhere (12 Nov 2026)

The light / dark / system theme button was only in the signed-in headers (and, in
the SMARTTT app, only on the Profile screens). It is now on every screen people land on:
the sign-in page (top right; `components/ThemeToggle` takes a className for light backgrounds), as well as the top bar as before.
