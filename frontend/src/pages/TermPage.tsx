import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { Download, Printer } from 'lucide-react'
import { errorBody, errorMessage } from '@/lib/api'
import { DAYS, FIRST_HOUR, HOURS, SCORE_LABELS, dateTime, termText } from '@/lib/format'
import { BulkPaste } from '@/components/BulkPaste'
import { DepartmentSubmissions } from '@/components/DepartmentSubmissions'
import { rememberTerm } from '@/lib/lastTerm'
import { printPdf } from '@/lib/print'
import {
  exportUrl,
  useBulkClassRows,
  useBulkOfferings,
  useClassRows,
  useDeleteClassRow,
  useDeleteGroup,
  useDeleteOffering,
  useDepartments,
  useImport,
  useOfferings,
  usePatchOffering,
  usePatchRow,
  useProposeGroups,
  useRuns,
  useSaveGroup,
  useSendPublication,
  useSnapshot,
  useStartRun,
  useTerm,
} from '@/lib/queries'
import type { ClassRow, Group, Offering, RoomType } from '@/lib/types'
import { CLASS_ROW_COLUMNS, ClassRowForm, OfferingForm, TermDetails, UNIT_COLUMNS } from './TermEntry'

const ROOM_TYPE_NAMES: Record<RoomType, string> = { lecture_hall: 'Lecture hall', lab: 'Lab', seminar: 'Seminar' }

const TABS = [
  ['setup', 'Term details'],
  ['departments', 'Departments'],
  ['rows', 'Class rows'],
  ['units', 'Units and groups'],
  ['runs', 'Generate'],
  ['drafts', 'Timetables and downloads'],
] as const
type Tab = (typeof TABS)[number][0]

export function TermPage() {
  const { termId = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const tab = (search.get('tab') as Tab | null) ?? 'setup'
  const term = useTerm(termId)
  // The app opens on this term next time (Home).
  useEffect(() => { if (term.isSuccess) rememberTerm(termId) }, [term.isSuccess, termId])

  if (term.isPending) return <p className="text-sm text-muted">Loading the term…</p>
  if (term.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(term.error)}</p>

  return (
    <div className="space-y-4">
      <div>
        <Link to="/terms" className="text-sm text-brand-ink">Switch term</Link>
        <h1 className="text-xl font-semibold">{term.data.name || termText(term.data)}</h1>
      </div>
      <div className="flex flex-wrap gap-1 border-b border-line">
        {TABS.map(([t, label]) => (
          <button key={t} onClick={() => setSearch({ tab: t })}
            className={clsx('-mb-px border-b-2 px-3 py-2 text-sm font-medium', tab === t ? 'border-brand-ink text-brand-ink' : 'border-transparent text-muted')}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'setup' && (
        <div className="space-y-4">
          <TermDetails termId={termId} />
          <SetupTab termId={termId} fromSmarttt={Boolean(term.data.smarttt_term_id)} />
        </div>
      )}
      {tab === 'departments' && <DepartmentSubmissions termId={termId} />}
      {tab === 'rows' && <RowsTab termId={termId} />}
      {tab === 'units' && <UnitsTab termId={termId} />}
      {tab === 'runs' && <RunsTab termId={termId} />}
      {tab === 'drafts' && <DraftsTab termId={termId} />}
    </div>
  )
}

function SetupTab({ termId, fromSmarttt }: { termId: string; fromSmarttt: boolean }) {
  const term = useTerm(termId)
  const snapshot = useSnapshot(termId)
  const importSetup = useImport(termId)
  const propose = useProposeGroups(termId)
  const readiness = term.data?.readiness
  const snap = readiness?.snapshot

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {fromSmarttt && (<>
      <section className="space-y-3 rounded-lg border border-line bg-card p-4">
        <h2 className="font-semibold">Optional: import from SMARTTT</h2>
        <p className="text-sm text-muted">Copies rooms, programmes, units, curricula, class sizes, lecturer counts and the current published timetable.</p>
        {snap ? (
          <p className="text-sm">Taken {dateTime(snap.taken_at)} by {snap.taken_by}: {snap.counts.rooms} rooms, {snap.counts.units} units,{' '}
            {snap.counts.programs} programmes; published version {snap.published_version ?? 'none'}.</p>
        ) : <p className="text-sm text-warning">No snapshot yet.</p>}
        <button onClick={() => snapshot.mutate(undefined)} disabled={snapshot.isPending}
          className="rounded-md bg-brand px-3 py-2 text-sm text-white disabled:opacity-50">
          {snapshot.isPending ? 'Reading SMARTTT…' : 'Take a new snapshot'}
        </button>
        {snapshot.isError && <p role="alert" className="text-sm text-danger">{errorMessage(snapshot.error)}</p>}
        {snap && snap.warnings.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer text-warning">{snap.warnings.length} data warnings from SMARTTT</summary>
            <ul className="mt-2 max-h-48 list-disc overflow-y-auto pl-5 text-ink">
              {snap.warnings.map((w) => <li key={w.detail}>{w.detail}</li>)}
            </ul>
          </details>
        )}
      </section>

      <section className="space-y-3 rounded-lg border border-line bg-card p-4">
        <h2 className="font-semibold">Add class rows, units, halls and departments from the snapshot</h2>
        <p className="text-sm text-muted">Adds what is missing. Anything entered here is never overwritten.</p>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => importSetup.mutate(undefined)} disabled={importSetup.isPending || !snap}
            className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-50">Import from the snapshot</button>
          <button onClick={() => propose.mutate(false)} disabled={propose.isPending || !snap}
            className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-50">Propose groups for new units</button>
        </div>
        {importSetup.isSuccess && (
          <p className="text-sm text-success">Added {importSetup.data.class_rows_created} class rows and {importSetup.data.offerings_created} units.
            {importSetup.data.unresolved.length > 0 && ` ${importSetup.data.unresolved.length} items need attention.`}</p>
        )}
        {propose.isSuccess && (
          <p className="text-sm text-success">Proposed groups for {propose.data.proposed} units.
            {propose.data.skipped.length > 0 && ` Skipped ${propose.data.skipped.length}: ${propose.data.skipped.slice(0, 5).map((s) => `${s.unit_code} (${s.reason})`).join('; ')}`}</p>
        )}
        {(importSetup.isError || propose.isError) && <p role="alert" className="text-sm text-danger">{errorMessage(importSetup.error ?? propose.error)}</p>}
      </section>
      </>)}

      <section className="space-y-2 rounded-lg border border-line bg-card p-4 lg:col-span-2">
        <h2 className="font-semibold">Ready to generate?</h2>
        {readiness?.ready
          ? <p className="text-sm text-success">Everything is set. Generate the timetable on the Generate tab.</p>
          : (
            <>
              <p className="text-sm text-warning">{readiness?.problem_count ?? readiness?.problems.length} things to fix first:</p>
              <ul className="max-h-64 list-disc overflow-y-auto pl-5 text-sm text-ink">
                {readiness?.problems.map((p, i) => <li key={`${p.code}${i}`}>{p.message}</li>)}
              </ul>
            </>
          )}
      </section>
    </div>
  )
}

function RowsTab({ termId }: { termId: string }) {
  const rows = useClassRows(termId)
  const patch = usePatchRow(termId)
  const remove = useDeleteClassRow(termId)
  const bulk = useBulkClassRows(termId)
  const offerings = useOfferings(termId)
  const departments = useDepartments()
  const deptCode = new Map((departments.data ?? []).map((d) => [d.id, d.code]))
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<ClassRow | null>(null)
  const [form, setForm] = useState<ClassRow | 'new' | null>(null)
  const [pasting, setPasting] = useState(false)
  const [deleted, setDeleted] = useState<string | null>(null)
  const shown = (rows.data ?? []).filter((r) => r.label.toLowerCase().includes(query.trim().toLowerCase()))

  const confirmDelete = (r: ClassRow) => {
    const taken = (offerings.data ?? []).filter((o) => o.class_row_ids.includes(r.id))
    const only = taken.filter((o) => o.class_row_ids.length === 1).map((o) => o.unit_code)
    const shared = taken.filter((o) => o.class_row_ids.length > 1).map((o) => o.unit_code)
    const lines = [`Delete ${r.label}?`]
    if (only.length) lines.push(`This also deletes ${only.length === 1 ? 'its unit' : `its ${only.length} units`}: ${only.join(', ')}.`)
    if (shared.length) lines.push(`It is taken off ${shared.join(', ')}, which other class rows keep.`)
    if (taken.length) lines.push('Draft timetables lose these classes; approved versions do not change.')
    if (!window.confirm(lines.join('\n\n'))) return
    setDeleted(null)
    remove.mutate(r.id, {
      onSuccess: (result) => setDeleted(`Deleted ${r.label}${result.units_deleted.length
        ? ` and ${result.units_deleted.length === 1 ? 'its unit' : `${result.units_deleted.length} units`} (${result.units_deleted.join(', ')})` : ''}.`),
    })
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter class rows"
          className="w-72 rounded-md border border-line px-3 py-1.5 text-sm" />
        <div className="flex gap-2 text-sm">
          <button onClick={() => setPasting(true)} className="rounded-md border border-line bg-card px-3 py-2">Paste from Excel</button>
          <button onClick={() => setForm('new')} className="rounded-md bg-brand px-3 py-2 text-white">+ Add a class row</button>
        </div>
      </div>
      {(patch.isError || remove.isError) && <p role="alert" className="text-sm text-danger">{errorMessage(patch.error ?? remove.error)}</p>}
      {deleted && <p role="status" className="text-sm text-success">{deleted}</p>}
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr><th className="px-3 py-2">Class row</th><th className="px-3 py-2">Department</th><th className="px-3 py-2">Students</th><th className="px-3 py-2">Unavailable hours</th><th /></tr>
          </thead>
          <tbody>
            {rows.data?.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-muted">No class rows yet. Add them one by one or paste them from Excel.</td></tr>
            )}
            {shown.map((r) => (
              <tr key={r.id} className="border-t border-line">
                <td className="px-3 py-2 font-medium">{r.label}{r.from_allocator && <span className="ml-1 rounded bg-brand-soft px-1 text-xs text-brand-ink" title="Entered by its department in Smart Attendance; the department edits it there">from its department</span>}</td>
                <td className="px-3 py-2 text-muted">{r.department_id != null ? deptCode.get(r.department_id) ?? '?' : '—'}</td>
                <td className="px-3 py-2">
                  {r.from_allocator ? r.student_count : <input type="number" min={0} defaultValue={r.student_count ?? ''} aria-label={`Students in ${r.label}`}
                    onBlur={(e) => {
                      const v = e.target.value === '' ? null : Number(e.target.value)
                      if (v !== null && v !== r.student_count) patch.mutate({ id: r.id, body: { student_count: v } })
                    }}
                    className={clsx('w-24 rounded-md border px-2 py-1', r.student_count == null ? 'border-warning/40' : 'border-line')} />}
                </td>
                <td className="px-3 py-2 text-muted">{r.unavailable.length ? `${r.unavailable.length} hours` : '—'}</td>
                <td className="space-x-3 whitespace-nowrap px-3 py-2 text-right">
                  <button onClick={() => setEditing(r)} className="text-brand-ink">Unavailable hours</button>
                  {!r.from_allocator && <button onClick={() => setForm(r)} className="text-brand-ink">Edit</button>}
                  {!r.from_allocator && (
                    <button onClick={() => confirmDelete(r)} disabled={remove.isPending} className="text-danger disabled:opacity-50">Delete</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && <UnavailableEditor row={editing} onClose={() => setEditing(null)}
        onSave={(slots) => patch.mutate({ id: editing.id, body: { unavailable: slots } }, { onSuccess: () => setEditing(null) })} />}
      {form && <ClassRowForm termId={termId} row={form === 'new' ? null : form} onClose={() => setForm(null)} />}
      {pasting && (
        <BulkPaste title="Paste class rows" columns={CLASS_ROW_COLUMNS} templateName="class-rows.csv"
          submit={(r) => bulk.mutateAsync(r)} onClose={() => setPasting(false)} />
      )}
    </div>
  )
}

function UnavailableEditor({ row, onClose, onSave }: { row: ClassRow; onClose: () => void; onSave: (slots: number[]) => void }) {
  const [slots, setSlots] = useState(new Set(row.unavailable))
  const toggle = (s: number) => setSlots((prev) => { const next = new Set(prev); if (next.has(s)) next.delete(s); else next.add(s); return next })
  return (
    <div role="dialog" aria-modal="true" aria-label={`Unavailable hours of ${row.label}`} className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-3xl rounded-xl bg-card p-5 shadow-xl">
        <h2 className="text-lg font-semibold">{row.label}</h2>
        <p className="text-sm text-muted">Click the hours when this class row cannot be taught (e.g. teaching practice).</p>
        <table className="mt-3 text-xs">
          <thead><tr><th />{Array.from({ length: HOURS }, (_, h) => <th key={h} className="px-1">{FIRST_HOUR + h}</th>)}</tr></thead>
          <tbody>
            {DAYS.map((d, di) => (
              <tr key={d}>
                <th className="pr-2 text-left">{d}</th>
                {Array.from({ length: HOURS }, (_, h) => {
                  const s = di * HOURS + h
                  return <td key={h}><button aria-pressed={slots.has(s)} aria-label={`${d} ${FIRST_HOUR + h}:00`} onClick={() => toggle(s)}
                    className={clsx('h-6 w-8 rounded border', slots.has(s) ? 'border-danger/40 bg-danger-soft' : 'border-line bg-surface')} /></td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-md border border-line px-3 py-2 text-sm">Cancel</button>
          <button onClick={() => onSave([...slots].sort((a, b) => a - b))} className="rounded-md bg-brand px-4 py-2 text-sm text-white">Save</button>
        </div>
      </div>
    </div>
  )
}

function UnitsTab({ termId }: { termId: string }) {
  const offerings = useOfferings(termId)
  const rows = useClassRows(termId)
  const patch = usePatchOffering(termId)
  const remove = useDeleteOffering(termId)
  const bulk = useBulkOfferings(termId)
  const departments = useDepartments()
  const deptCode = new Map((departments.data ?? []).map((d) => [d.id, d.code]))
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<Offering | null>(null)
  const [form, setForm] = useState<Offering | 'new' | null>(null)
  const [pasting, setPasting] = useState(false)
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (offerings.data ?? []).filter((o) => !q || o.unit_code.toLowerCase().includes(q) || o.unit_name.toLowerCase().includes(q))
  }, [offerings.data, query])
  const current = open ? offerings.data?.find((o) => o.id === open.id) ?? open : null

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter units"
          className="w-72 rounded-md border border-line px-3 py-1.5 text-sm" />
        <div className="flex gap-2 text-sm">
          <button onClick={() => setPasting(true)} className="rounded-md border border-line bg-card px-3 py-2">Paste from Excel</button>
          <button onClick={() => setForm('new')} className="rounded-md bg-brand px-3 py-2 text-white">+ Add a unit</button>
        </div>
      </div>
      {(patch.isError || remove.isError) && <p role="alert" className="text-sm text-danger">{errorMessage(patch.error ?? remove.error)}</p>}
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr><th className="px-3 py-2">Unit</th><th className="px-3 py-2">Department</th><th className="px-3 py-2">Class rows</th><th className="px-3 py-2">Hours / week</th>
              <th className="px-3 py-2">Session</th><th className="px-3 py-2">Room type</th><th className="px-3 py-2">Groups</th><th /></tr>
          </thead>
          <tbody>
            {offerings.data?.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-6 text-center text-muted">No units yet. Add them one by one or paste them from Excel.</td></tr>
            )}
            {shown.map((o) => (
              <tr key={o.id} className="border-t border-line">
                <td className="px-3 py-2"><span className="font-medium">{o.unit_code}</span>{o.from_allocator && <span className="ml-1 rounded bg-brand-soft px-1 text-xs text-brand-ink" title="Entered by its department in Smart Attendance; the department edits it there">from its department</span>}<span className="block text-muted">{o.unit_name}</span></td>
                <td className="px-3 py-2 text-muted">{deptCode.get(o.department_id) ?? '?'}</td>
                <td className="px-3 py-2 text-muted">{o.class_rows.join(', ')}</td>
                <td className="px-3 py-2">
                  {o.from_allocator ? o.weekly_hours : <input type="number" min={1} max={20} defaultValue={o.weekly_hours ?? ''} aria-label={`Weekly hours of ${o.unit_code}`}
                    onBlur={(e) => e.target.value && Number(e.target.value) !== o.weekly_hours && patch.mutate({ id: o.id, body: { weekly_hours: Number(e.target.value) } })}
                    className={clsx('w-16 rounded-md border px-2 py-1', o.weekly_hours == null ? 'border-warning/40' : 'border-line')} />}
                </td>
                <td className="px-3 py-2">
                  {o.from_allocator ? o.session_length : <input type="number" min={1} max={6} defaultValue={o.session_length ?? ''} aria-label={`Session length of ${o.unit_code}`}
                    onBlur={(e) => e.target.value && Number(e.target.value) !== o.session_length && patch.mutate({ id: o.id, body: { session_length: Number(e.target.value) } })}
                    className={clsx('w-16 rounded-md border px-2 py-1', o.session_length == null ? 'border-warning/40' : 'border-line')} />}
                </td>
                <td className="px-3 py-2">
                  {o.from_allocator ? ROOM_TYPE_NAMES[o.room_type] : <select value={o.room_type} aria-label={`Room type of ${o.unit_code}`}
                    onChange={(e) => patch.mutate({ id: o.id, body: { room_type: e.target.value as RoomType } })}
                    className="rounded-md border border-line px-2 py-1">
                    <option value="lecture_hall">Lecture hall</option><option value="lab">Lab</option><option value="seminar">Seminar</option>
                  </select>}
                </td>
                <td className="px-3 py-2">
                  <button onClick={() => setOpen(o)} className={clsx(o.groups.length ? 'text-brand-ink' : 'text-warning')}>
                    {o.groups.length ? o.groups.map((g) => g.label || 'Whole class').join(', ') : 'Set groups'}
                  </button>
                </td>
                <td className="space-x-3 whitespace-nowrap px-3 py-2 text-right">
                  {!o.from_allocator && <button onClick={() => setForm(o)} className="text-brand-ink">Edit</button>}
                  {!o.from_allocator && (
                    <button onClick={() => {
                      if (window.confirm(`Delete ${o.unit_code}?\n\nDraft timetables lose its classes; approved versions do not change.`)) remove.mutate(o.id)
                    }} disabled={remove.isPending} className="text-danger disabled:opacity-50">Delete</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {current && <GroupsEditor offering={current} rows={rows.data ?? []} termId={termId} onClose={() => setOpen(null)} />}
      {form && <OfferingForm termId={termId} offering={form === 'new' ? null : form} rows={rows.data ?? []} onClose={() => setForm(null)} />}
      {pasting && (
        <BulkPaste title="Paste units" columns={UNIT_COLUMNS} templateName="units.csv"
          submit={(r) => bulk.mutateAsync(r)} onClose={() => setPasting(false)} />
      )}
    </div>
  )
}

function GroupsEditor({ offering, rows, termId, onClose }: { offering: Offering; rows: ClassRow[]; termId: string; onClose: () => void }) {
  const save = useSaveGroup(termId)
  const remove = useDeleteGroup(termId)
  const eligible = rows.filter((r) => offering.class_row_ids.includes(r.id))
  const blank = (): Group => ({ id: '', label: '', student_count: 0, members: [] })
  const [draft, setDraft] = useState<Group | null>(null)
  const failure = errorBody(save.error)

  return (
    <div role="dialog" aria-modal="true" aria-label={`Groups of ${offering.unit_code}`} className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 px-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-card p-5 shadow-xl">
        <h2 className="text-lg font-semibold">{offering.unit_code} groups</h2>
        <p className="text-sm text-muted">
          {offering.from_allocator
            ? 'Its department decided the split and the lecturers in Smart Attendance; the department changes them there.'
            : 'You decide the split. Each group is one class with its own room and lecturer.'}
        </p>
        <ul className="mt-3 space-y-2">
          {offering.groups.map((g) => (
            <li key={g.id} className="flex items-start justify-between rounded-md border border-line p-2 text-sm">
              <span><b>{g.label || 'Whole class'}</b> · {g.student_count} students
                <span className="block text-muted">{g.members.map((m) => `${m.label} (${m.students})`).join(', ')}</span>
                {g.lecturer_name && <span className="block">{g.lecturer_name}{g.lecturer_staff_number ? ` · ${g.lecturer_staff_number}` : ''}</span>}</span>
              {!offering.from_allocator && (
                <span className="flex gap-2">
                  <button onClick={() => setDraft(g)} className="text-brand-ink">Edit</button>
                  <button onClick={() => remove.mutate(g.id)} className="text-danger">Remove</button>
                </span>
              )}
            </li>
          ))}
        </ul>
        {!offering.from_allocator && <button onClick={() => setDraft(blank())} className="mt-2 text-sm text-brand-ink">+ Add a group</button>}

        {draft && (
          <div className="mt-4 space-y-2 rounded-md border border-line p-3 text-sm">
            <label className="block">Label (blank for the whole class)
              <input value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} placeholder="GR A"
                className="mt-1 w-40 rounded-md border border-line px-2 py-1" />
            </label>
            {eligible.map((r) => {
              const member = draft.members.find((m) => m.class_row_id === r.id)
              return (
                <label key={r.id} className="flex items-center gap-2">
                  <input type="checkbox" checked={Boolean(member)} onChange={(e) => setDraft({
                    ...draft,
                    members: e.target.checked
                      ? [...draft.members, { class_row_id: r.id, label: r.label, students: r.student_count ?? 1 }]
                      : draft.members.filter((m) => m.class_row_id !== r.id),
                  })} />
                  <span className="flex-1">{r.label}</span>
                  {member && <input type="number" min={1} value={member.students} aria-label={`Students from ${r.label}`}
                    onChange={(e) => setDraft({ ...draft, members: draft.members.map((m) => m.class_row_id === r.id ? { ...m, students: Number(e.target.value) } : m) })}
                    className="w-20 rounded-md border border-line px-2 py-1" />}
                </label>
              )
            })}
            {failure && <p role="alert" className="text-danger">{failure.message}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={() => setDraft(null)} className="rounded-md border border-line px-3 py-1">Cancel</button>
              <button disabled={!draft.members.length || save.isPending}
                onClick={() => save.mutate({ offeringId: offering.id, groupId: draft.id || undefined,
                  body: { label: draft.label, members: draft.members.map((m) => ({ class_row_id: m.class_row_id, students: m.students })) } },
                { onSuccess: () => setDraft(null) })}
                className="rounded-md bg-brand px-3 py-1 text-white disabled:opacity-50">Save group</button>
            </div>
          </div>
        )}
        <div className="mt-4 flex justify-end"><button onClick={onClose} className="rounded-md border border-line px-3 py-2 text-sm">Done</button></div>
      </div>
    </div>
  )
}

function RunsTab({ termId }: { termId: string }) {
  const runs = useRuns(termId)
  const start = useStartRun(termId)
  const [mode, setMode] = useState<'full' | 'repair'>('full')
  const [minutes, setMinutes] = useState(10)
  const failure = errorBody(start.error)
  const problems = (failure?.details as { problems?: { message: string }[] } | undefined)?.problems

  return (
    <div className="space-y-4">
      <section className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-card p-4 text-sm">
        <label>Run
          <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} className="mt-1 block rounded-md border border-line px-2 py-1">
            <option value="full">Full solve</option>
            <option value="repair">Repair the published timetable (mid-term change)</option>
          </select>
        </label>
        <label>Time limit (minutes)
          <input type="number" min={1} max={60} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}
            className="mt-1 block w-24 rounded-md border border-line px-2 py-1" />
        </label>
        <button onClick={() => start.mutate({ mode, time_limit_s: minutes * 60 })} disabled={start.isPending}
          className="rounded-md bg-brand px-4 py-2 font-medium text-white disabled:opacity-50">Start</button>
        {failure && <p role="alert" className="w-full text-danger">{failure.message}
          {problems && <span className="block">{problems.slice(0, 5).map((p) => p.message).join('; ')}</span>}</p>}
      </section>
      <ul className="space-y-2">
        {(runs.data ?? []).map((r) => (
          <li key={r.id} className="rounded-lg border border-line bg-card p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span><b className="capitalize">{r.mode}</b> run · started {dateTime(r.created_at)} by {r.created_by}</span>
              <span className={clsx('rounded px-2 py-0.5 text-xs font-medium',
                r.status === 'succeeded' ? 'bg-success-soft text-success' : r.status === 'failed' ? 'bg-danger-soft text-danger' : 'bg-brand-soft text-brand-ink')}>
                {r.status}{(r.status === 'running' && r.progress.seconds != null) ? ` · ${r.progress.phase} ${r.progress.seconds}s` : ''}
              </span>
            </div>
            {r.status === 'succeeded' && r.draft_id && (
              <p className="mt-1">{SCORE_LABELS.slice(0, 5).map(([k, l]) => `${l}: ${r.soft_scores[k] ?? 0}`).join(' · ')}{' '}
                <Link to={`/terms/${termId}/drafts/${r.draft_id}`} className="text-brand-ink">Review the draft →</Link></p>
            )}
            {r.failure && (
              <ul className="mt-1 list-disc pl-5 text-danger">
                {r.failure.reasons.slice(0, 10).map((x, i) => <li key={i}>{x.message}</li>)}
                {r.failure.count > 10 && <li>…and {r.failure.count - 10} more</li>}
              </ul>
            )}
          </li>
        ))}
        {runs.data?.length === 0 && <li className="text-sm text-muted">No runs yet.</li>}
      </ul>
    </div>
  )
}

function DraftsTab({ termId }: { termId: string }) {
  const term = useTerm(termId)
  const send = useSendPublication(termId)
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="rounded-lg border border-line bg-card p-4">
        <h2 className="mb-2 font-semibold">Drafts</h2>
        <ul className="space-y-1 text-sm">
          {term.data?.drafts.map((d) => (
            <li key={d.id} className="flex justify-between">
              <Link to={`/terms/${termId}/drafts/${d.id}`} className="text-brand-ink">{d.name}</Link>
              <span className="text-muted">{d.status} · {dateTime(d.created_at)}</span>
            </li>
          ))}
          {term.data?.drafts.length === 0 && <li className="text-muted">None yet.</li>}
        </ul>
      </section>
      <section className="rounded-lg border border-line bg-card p-4">
        <h2 className="mb-2 font-semibold">Published versions</h2>
        <ul className="space-y-1 text-sm">
          {term.data?.publications.map((p) => (
            <li key={p.version} className="space-y-0.5">
              <b>Version {p.version}</b> · {dateTime(p.published_at)} by {p.published_by}
              {p.changes && <span className="block text-muted">{p.changes.added?.length ?? 0} added, {p.changes.moved?.length ?? 0} moved, {p.changes.removed?.length ?? 0} removed</span>}
              {!p.sent_to_smarttt && <span className="block text-warning">Approved here, not yet in SMARTTT{p.not_sent_reason ? `: ${p.not_sent_reason}` : ''}</span>}
              {p.can_send && (
                <button onClick={() => send.mutate(p.version)} disabled={send.isPending}
                  className="rounded-md border border-warning/40 bg-warning-soft px-2 py-1 text-warning disabled:opacity-50">
                  {send.isPending ? 'Sending…' : 'Send to SMARTTT now'}
                </button>
              )}
              <span className="flex flex-wrap items-center gap-3">
                Download:
                {([['pdf', 'PDF'], ['docx', 'Word'], ['xlsx', 'Excel']] as const).map(([format, label]) => (
                  <a key={format} href={exportUrl(p.draft_id, 'row', format)} className="inline-flex items-center gap-1 text-brand-ink">
                    <Download size={14} aria-hidden /> {label}
                  </a>
                ))}
                <PrintButton draftId={p.draft_id} />
              </span>
            </li>
          ))}
          {term.data?.publications.length === 0 && <li className="text-muted">Nothing published yet.</li>}
        </ul>
        {send.isError && <p role="alert" className="mt-2 text-sm text-danger">{errorMessage(send.error)}</p>}
      </section>
    </div>
  )
}


/** Prints the approved version as the PDF download lays it out (by class row). */
function PrintButton({ draftId }: { draftId: string }) {
  const [state, setState] = useState<'idle' | 'preparing' | 'failed'>('idle')
  const print = () => {
    setState('preparing')
    printPdf(`/drafts/${draftId}/export.pdf?view=row`).then(() => setState('idle'), () => setState('failed'))
  }
  return (
    <>
      <button type="button" onClick={print} disabled={state === 'preparing'}
        className="inline-flex items-center gap-1 text-brand-ink disabled:opacity-60">
        <Printer size={14} aria-hidden /> {state === 'preparing' ? 'Preparing…' : 'Print'}
      </button>
      {state === 'failed' && <span role="alert" className="text-danger">Couldn't prepare the timetable to print. Try again, or download the PDF.</span>}
    </>
  )
}
