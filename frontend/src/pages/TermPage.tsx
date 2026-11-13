import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { AlertTriangle, ArrowLeft, ArrowRight, BookOpen, Check, CheckCircle2, Layers, Play, Send } from 'lucide-react'
import { errorBody, errorMessage } from '@/lib/api'
import { DAYS, FIRST_HOUR, HOURS, SCORE_LABELS, dateTime, termText } from '@/lib/format'
import { BulkPaste } from '@/components/BulkPaste'
import { DepartmentSubmissions } from '@/components/DepartmentSubmissions'
import { DownloadMenu } from '@/components/DownloadMenu'
import { ExamGenerateStep, ExamPapersStep, ExamPeriodStep, ExamPublishStep } from '@/components/ExamSteps'
import { Card, IconBox, Notice, PageTitle, PanelButton, Pill, btn, type Tone } from '@/components/ui'
import { rememberTerm } from '@/lib/lastTerm'
import { printPdf } from '@/lib/print'
import { LEGACY_TABS, STEPS, useExamProgress, useTeachingProgress, type Mode } from '@/lib/steps'
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
  useRoomList,
  useRuns,
  useSaveGroup,
  useSendPublication,
  useSnapshot,
  useStartRun,
  useTerm,
} from '@/lib/queries'
import type { ClassRow, Group, Offering, PublicationItem, RoomType, Run, TermOverview } from '@/lib/types'
import { CLASS_ROW_COLUMNS, ClassRowForm, CopyFromTerm, OfferingForm, TermDetailsForm, UNIT_COLUMNS } from './TermEntry'

const ROOM_TYPE_NAMES: Record<RoomType, string> = { lecture_hall: 'Lecture hall', lab: 'Lab', seminar: 'Seminar' }

/**
 * A term, worked through step by step: teaching (details, departments, classes and units, generate,
 * review and publish) or exams. Each step shows a summary and its one main action; lists and forms
 * open in a side panel. The URL keeps the place (?mode=exams&step=2); old ?tab= links still work.
 */
export function TermPage() {
  const { termId = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const term = useTerm(termId)
  const legacy = LEGACY_TABS[search.get('tab') ?? '']
  const mode: Mode = legacy?.mode ?? (search.get('mode') === 'exams' ? 'exams' : 'teaching')
  const teaching = useTeachingProgress(termId)
  const exams = useExamProgress(termId)
  const progress = mode === 'exams' ? exams : teaching
  const steps = STEPS[mode]
  const asked = Number(search.get('step')) || legacy?.step || 0
  const step = Math.min(steps.length, Math.max(1, asked || progress?.current || 1))
  const go = (m: Mode, s?: number) => setSearch(m === 'exams' ? { mode: m, ...(s ? { step: String(s) } : {}) } : s ? { step: String(s) } : {})
  // The app opens on this term next time (Home).
  useEffect(() => { if (term.isSuccess) rememberTerm(termId) }, [term.isSuccess, termId])

  if (term.isPending) return <p className="text-sm text-muted">Loading the term…</p>
  if (term.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(term.error)}</p>
  const t = term.data

  return (
    <div className="space-y-6">
      <PageTitle title={t.name || termText(t)} crumb="Terms" />
      <div className="flex flex-wrap items-center gap-3">
        <div role="group" aria-label="Timetable" className="inline-flex rounded-xl bg-brand-soft p-1">
          {(['teaching', 'exams'] as const).map((m) => (
            <button key={m} type="button" aria-pressed={mode === m} onClick={() => go(m)}
              className={clsx('rounded-lg px-5 py-2 text-sm font-semibold', mode === m ? 'bg-card text-brand-ink shadow-sm' : 'text-muted hover:text-ink')}>
              {m === 'teaching' ? 'Teaching' : 'Exams'}
            </button>
          ))}
        </div>
        <span className="text-sm text-muted">{termText(t)}{t.start_date && t.end_date ? ` · ${dateRange(t.start_date, t.end_date)}` : ''}</span>
        <Link to="/terms" className={clsx(btn.quiet, 'ml-auto')}>Switch term</Link>
      </div>

      <ol aria-label="Steps" className="grid gap-2 rounded-xl border border-line bg-card p-3 sm:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))]">
        {steps.map((s, i) => {
          const n = i + 1
          const done = progress?.done[i] ?? false
          const active = n === step
          return (
            <li key={s.key}>
              <button type="button" onClick={() => go(mode, n)} aria-current={active ? 'step' : undefined}
                className={clsx('flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-sm font-semibold',
                  active ? 'bg-brand-soft text-brand-ink' : done ? 'text-ink hover:bg-surface' : 'text-muted hover:bg-surface')}>
                <span className={clsx('grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold',
                  done ? 'bg-success text-white dark:text-brand-950' : active ? 'bg-brand text-white' : 'bg-surface text-muted')}>
                  {done ? <Check className="size-4" strokeWidth={3} aria-label="done" /> : n}
                </span>
                {s.label}
              </button>
            </li>
          )
        })}
      </ol>

      {mode === 'teaching' && step === 1 && <DetailsStep term={t} />}
      {mode === 'teaching' && step === 2 && <DepartmentSubmissions termId={termId} />}
      {mode === 'teaching' && step === 3 && <ClassesStep term={t} onNext={() => go('teaching', 4)} />}
      {mode === 'teaching' && step === 4 && <GenerateStep termId={termId} />}
      {mode === 'teaching' && step === 5 && <PublishStep term={t} />}
      {mode === 'exams' && step === 1 && <ExamPeriodStep termId={termId} />}
      {mode === 'exams' && step === 2 && <ExamPapersStep termId={termId} />}
      {mode === 'exams' && step === 3 && <ExamGenerateStep termId={termId} />}
      {mode === 'exams' && step === 4 && <ExamPublishStep termId={termId} />}

      <div className="flex flex-wrap justify-between gap-2">
        {step > 1 ? <button type="button" onClick={() => go(mode, step - 1)} className={btn.secondary}><ArrowLeft className="size-4" aria-hidden /> Back</button> : <span />}
        {step < steps.length && (
          <button type="button" onClick={() => go(mode, step + 1)} className={btn.secondary}>Next: {steps[step].label.toLowerCase()} <ArrowRight className="size-4" aria-hidden /></button>
        )}
      </div>
    </div>
  )
}

const dateRange = (a: string, b: string) => {
  const f = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
  return `${f(a)} – ${f(b)}`
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><dt className="text-sm text-muted">{label}</dt><dd className="mt-0.5 text-[15px]">{children || '—'}</dd></div>
}

// -- step 1: term details ------------------------------------------------------------------

function DetailsStep({ term }: { term: TermOverview }) {
  const rooms = useRoomList()
  const departments = useDepartments()
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Term details">
        <dl className="grid grid-cols-2 gap-4">
          <Detail label="Name on the timetable">{term.name}</Detail>
          <Detail label="Dates">{term.start_date && term.end_date ? dateRange(term.start_date, term.end_date) : ''}</Detail>
          <Detail label="Class length">{`${term.default_session_length} hours`}</Detail>
          <Detail label="Prepared by">{[term.prepared_by, term.prepared_by_title].filter(Boolean).join(', ')}</Detail>
        </dl>
        <div className="flex flex-wrap gap-2">
          <PanelButton label="Edit details" title="Term details" className={btn.primary}><TermDetailsForm term={term} key={term.id} /></PanelButton>
          <PanelButton label="Copy from a previous term" title="Start from a previous term"><CopyFromTerm termId={term.id} /></PanelButton>
        </div>
      </Card>
      <Card title="Shared by every term">
        <div className="grid gap-3 sm:grid-cols-2">
          <Link to="/rooms" className="flex items-center gap-3 rounded-lg bg-surface p-3 hover:bg-brand-soft">
            <span className="text-2xl font-bold">{rooms.data?.length ?? '–'}</span><span className="text-sm text-muted">lecture halls</span>
          </Link>
          <Link to="/departments" className="flex items-center gap-3 rounded-lg bg-surface p-3 hover:bg-brand-soft">
            <span className="text-2xl font-bold">{departments.data?.length ?? '–'}</span><span className="text-sm text-muted">departments</span>
          </Link>
        </div>
      </Card>
      {term.smarttt_term_id && <SmartttCard term={term} />}
    </div>
  )
}

function SmartttCard({ term }: { term: TermOverview }) {
  const snapshot = useSnapshot(term.id)
  const importSetup = useImport(term.id)
  const propose = useProposeGroups(term.id)
  const snap = term.readiness.snapshot
  return (
    <Card title="Bring in data from SMARTTT" className="lg:col-span-2"
      action={snap && snap.warnings.length > 0 && (
        <PanelButton label={`${snap.warnings.length} data warnings`} title="Data warnings from SMARTTT" icon={AlertTriangle} className={btn.quiet}>
          <ul className="list-disc space-y-1 pl-5 text-sm">{snap.warnings.map((w) => <li key={w.detail}>{w.detail}</li>)}</ul>
        </PanelButton>
      )}>
      <p className="text-sm text-muted">Optional. Copies rooms, programmes, units, curricula, class sizes, lecturer counts and the current published timetable.
        Adding from it never overwrites what was entered here.</p>
      {snap ? (
        <Pill tone="success"><Check className="size-3.5" aria-hidden /> Taken {dateTime(snap.taken_at)}: {snap.counts.rooms} rooms, {snap.counts.units} units, {snap.counts.programs} programmes</Pill>
      ) : <Pill tone="warning">No snapshot yet</Pill>}
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => snapshot.mutate(undefined)} disabled={snapshot.isPending} className={btn.primary}>
          {snapshot.isPending ? 'Reading SMARTTT…' : 'Take a new snapshot'}
        </button>
        <button type="button" onClick={() => importSetup.mutate(undefined)} disabled={importSetup.isPending || !snap} className={btn.secondary}>Add from the snapshot</button>
        <button type="button" onClick={() => propose.mutate(false)} disabled={propose.isPending || !snap} className={btn.secondary}>Propose groups for new units</button>
      </div>
      {importSetup.isSuccess && (
        <p role="status" className="text-sm text-success">Added {importSetup.data.class_rows_created} class rows and {importSetup.data.offerings_created} units.
          {importSetup.data.unresolved.length > 0 && ` ${importSetup.data.unresolved.length} items need attention.`}</p>
      )}
      {propose.isSuccess && (
        <p role="status" className="text-sm text-success">Proposed groups for {propose.data.proposed} units.
          {propose.data.skipped.length > 0 && ` Skipped ${propose.data.skipped.length}: ${propose.data.skipped.slice(0, 5).map((s) => `${s.unit_code} (${s.reason})`).join('; ')}`}</p>
      )}
      {(snapshot.isError || importSetup.isError || propose.isError) && (
        <p role="alert" className="text-sm text-danger">{errorMessage(snapshot.error ?? importSetup.error ?? propose.error)}</p>
      )}
    </Card>
  )
}

// -- step 3: classes and units ------------------------------------------------------------

function ClassesStep({ term, onNext }: { term: TermOverview; onNext: () => void }) {
  const rows = useClassRows(term.id)
  const offerings = useOfferings(term.id)
  const noStudents = (rows.data ?? []).filter((r) => r.student_count == null).length
  const noGroups = (offerings.data ?? []).filter((o) => o.groups.length === 0).length
  const readiness = term.readiness
  const tiles = [
    { icon: Layers, value: rows.data?.length, label: 'Class rows (programme, year and semester)', title: 'Class rows',
      note: noStudents ? `${noStudents} without a number of students` : '', body: <RowsTab termId={term.id} /> },
    { icon: BookOpen, value: offerings.data?.length, label: 'Units and their groups', title: 'Units and groups',
      note: noGroups ? `${noGroups} without a group` : '', body: <UnitsTab termId={term.id} /> },
  ]
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        {tiles.map((tile) => (
          <Card key={tile.title}>
            <div className="flex items-center gap-4">
              <IconBox icon={tile.icon} size="lg" />
              <div>
                <p className="text-3xl font-bold tracking-tight">{tile.value ?? '–'}</p>
                <p className="text-sm text-muted">{tile.label}</p>
              </div>
            </div>
            {tile.note && <Pill tone="warning">{tile.note}</Pill>}
            <PanelButton label="View and edit" title={tile.title} wide className={btn.primary}>{tile.body}</PanelButton>
          </Card>
        ))}
      </div>
      {readiness.ready ? (
        <Notice tone="success" icon={CheckCircle2} action={<button type="button" onClick={onNext} className={btn.primary}>Next: generate <ArrowRight className="size-4" aria-hidden /></button>}>
          Everything is set to generate.
        </Notice>
      ) : (
        <Notice icon={AlertTriangle} action={
          <PanelButton label="Show them" title="To fix before generating">
            <ul className="list-disc space-y-1.5 pl-5 text-sm">{readiness.problems.map((p, i) => <li key={`${p.code}${i}`}>{p.message}</li>)}</ul>
          </PanelButton>
        }>
          {readiness.problem_count ?? readiness.problems.length} things to fix before generating.
        </Notice>
      )}
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
          <button onClick={() => setPasting(true)} className={btn.secondary}>Paste from Excel</button>
          <button onClick={() => setForm('new')} className={btn.primary}>+ Add a class row</button>
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
          <button onClick={onClose} className={btn.secondary}>Cancel</button>
          <button onClick={() => onSave([...slots].sort((a, b) => a - b))} className={btn.primary}>Save</button>
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
          <button onClick={() => setPasting(true)} className={btn.secondary}>Paste from Excel</button>
          <button onClick={() => setForm('new')} className={btn.primary}>+ Add a unit</button>
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
              <button onClick={() => setDraft(null)} className={btn.secondary}>Cancel</button>
              <button disabled={!draft.members.length || save.isPending}
                onClick={() => save.mutate({ offeringId: offering.id, groupId: draft.id || undefined,
                  body: { label: draft.label, members: draft.members.map((m) => ({ class_row_id: m.class_row_id, students: m.students })) } },
                { onSuccess: () => setDraft(null) })}
                className={btn.primary}>Save group</button>
            </div>
          </div>
        )}
        <div className="mt-4 flex justify-end"><button onClick={onClose} className={btn.secondary}>Done</button></div>
      </div>
    </div>
  )
}

// -- step 4: generate ---------------------------------------------------------------------

const RUN_TONE: Record<Run['status'], Tone> = { succeeded: 'success', failed: 'danger', running: 'brand', queued: 'brand' }
const RUN_STATUS: Record<Run['status'], string> = { succeeded: 'Finished', failed: 'Failed', running: 'Running', queued: 'Waiting to start' }

function GenerateStep({ termId }: { termId: string }) {
  const runs = useRuns(termId)
  const start = useStartRun(termId)
  const [mode, setMode] = useState<'full' | 'repair'>('full')
  const [minutes, setMinutes] = useState(10)
  const failure = errorBody(start.error)
  const problems = (failure?.details as { problems?: { message: string }[] } | undefined)?.problems
  const teaching = (runs.data ?? []).filter((r) => r.mode !== 'exam')
  const latest = teaching[0]
  const choice = (value: typeof mode, title: string, hint: string) => (
    <button type="button" role="radio" aria-checked={mode === value} onClick={() => setMode(value)}
      className={clsx('flex flex-col items-start gap-0.5 rounded-xl border-2 px-4 py-3 text-left',
        mode === value ? 'border-brand bg-brand-soft' : 'border-line bg-card hover:border-brand-200')}>
      <span className="text-[15px] font-semibold">{title}</span>
      <span className="text-sm text-muted">{hint}</span>
    </button>
  )

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Generate the timetable">
        <div role="radiogroup" aria-label="Kind of run" className="grid gap-2">
          {choice('full', 'Full timetable', 'Start from scratch for the whole term')}
          {choice('repair', 'Repair the published one', 'A mid-term change; keeps everything else in place')}
        </div>
        <label className="flex items-center gap-3 text-sm text-muted">Stop after
          <input type="number" min={1} max={60} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}
            aria-label="Time limit in minutes" className="w-20 rounded-md border border-line px-3 py-1.5 text-ink" /> minutes
        </label>
        <button type="button" onClick={() => start.mutate({ mode, time_limit_s: minutes * 60 })} disabled={start.isPending} className={clsx(btn.gold, 'w-full')}>
          <Play className="size-5 fill-current" aria-hidden /> {start.isPending ? 'Starting…' : 'Generate'}
        </button>
        {failure && <p role="alert" className="text-sm text-danger">{failure.message}
          {problems && <span className="block">{problems.slice(0, 5).map((p) => p.message).join('; ')}</span>}</p>}
      </Card>
      <Card title="Last run" action={teaching.length > 1 && (
        <PanelButton label="All runs" title="Runs" className={btn.quiet}>
          <ul className="space-y-3">{teaching.map((r) => <li key={r.id}><RunSummary run={r} termId={termId} /></li>)}</ul>
        </PanelButton>
      )}>
        {latest ? <RunSummary run={latest} termId={termId} /> : <p className="text-sm text-muted">No runs yet.</p>}
      </Card>
    </div>
  )
}

function RunSummary({ run, termId }: { run: Run; termId: string }) {
  return (
    <div className="space-y-3 rounded-lg bg-surface p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Pill tone={RUN_TONE[run.status]}>
          {run.status === 'succeeded' && <Check className="size-3.5" aria-hidden />}
          {RUN_STATUS[run.status]}{run.status === 'running' && run.progress.seconds != null ? ` · ${run.progress.phase ?? ''} ${run.progress.seconds}s` : ''}
        </Pill>
        <span className="text-muted"><span className="capitalize">{run.mode}</span> · {dateTime(run.created_at)} by {run.created_by}</span>
      </div>
      {run.status === 'succeeded' && run.draft_id && (
        <>
          <p className="text-muted">{SCORE_LABELS.slice(0, 5).map(([k, l]) => `${l}: ${run.soft_scores[k] ?? 0}`).join(' · ')}</p>
          <Link to={`/terms/${termId}/drafts/${run.draft_id}`} className={btn.primary}>Review the draft <ArrowRight className="size-4" aria-hidden /></Link>
        </>
      )}
      {run.failure && (
        <ul className="list-disc pl-5 text-danger">
          {run.failure.reasons.slice(0, 10).map((x, i) => <li key={i}>{x.message}</li>)}
          {run.failure.count > 10 && <li>…and {run.failure.count - 10} more</li>}
        </ul>
      )}
    </div>
  )
}

// -- step 5: review and publish -----------------------------------------------------------

const DRAFT_TONE = { draft: 'brand', published: 'success', superseded: 'muted' } as const

function PublishStep({ term }: { term: TermOverview }) {
  const send = useSendPublication(term.id)
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Drafts">
        <ul className="space-y-2">
          {term.drafts.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-3 rounded-lg bg-surface px-4 py-3">
              <span className="min-w-0 flex-1">
                <span className="block font-semibold">{d.name}</span>
                <span className="block text-sm text-muted">{dateTime(d.created_at)} · {d.session_count} classes</span>
              </span>
              <Pill tone={DRAFT_TONE[d.status]}>{d.status}</Pill>
              <Link to={`/terms/${term.id}/drafts/${d.id}`} className={btn.secondary}>Open</Link>
            </li>
          ))}
          {term.drafts.length === 0 && <li className="text-sm text-muted">None yet. Generate one first.</li>}
        </ul>
        {term.drafts.length > 0 && <p className="text-sm text-muted">To publish, open a draft and choose Approve and publish.</p>}
      </Card>
      <Card title="Published">
        <ul className="space-y-2">
          {term.publications.map((p, i) => <PublishedVersion key={p.version} item={p} latest={i === 0} sending={send.isPending} onSend={() => send.mutate(p.version)} />)}
          {term.publications.length === 0 && <li className="text-sm text-muted">Nothing published yet.</li>}
        </ul>
        {send.isError && <p role="alert" className="text-sm text-danger">{errorMessage(send.error)}</p>}
      </Card>
    </div>
  )
}

function PublishedVersion({ item: p, latest, sending, onSend }: { item: PublicationItem; latest: boolean; sending: boolean; onSend: () => void }) {
  const [printing, setPrinting] = useState<'idle' | 'preparing' | 'failed'>('idle')
  const print = () => {
    setPrinting('preparing')
    printPdf(`/drafts/${p.draft_id}/export.pdf?view=row`).then(() => setPrinting('idle'), () => setPrinting('failed'))
  }
  return (
    <li className={clsx('space-y-2 rounded-lg px-4 py-3', latest ? 'bg-brand-soft' : 'bg-surface')}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="min-w-0 flex-1">
          <span className="block font-semibold">Version {p.version}</span>
          <span className="block text-sm text-muted">{dateTime(p.published_at)} by {p.published_by}
            {p.changes && ` · ${p.changes.added?.length ?? 0} added, ${p.changes.moved?.length ?? 0} moved, ${p.changes.removed?.length ?? 0} removed`}</span>
        </span>
        {p.sent_to_smarttt ? <Pill tone="success">On SMARTTT</Pill> : <Pill tone="warning">Not in SMARTTT</Pill>}
        <DownloadMenu items={[
          { label: 'PDF', href: exportUrl(p.draft_id, 'row', 'pdf') },
          { label: 'Word', href: exportUrl(p.draft_id, 'row', 'docx') },
          { label: 'Excel', href: exportUrl(p.draft_id, 'row', 'xlsx') },
          { label: printing === 'preparing' ? 'Preparing to print…' : 'Print', onClick: print, busy: printing === 'preparing' },
        ]} />
      </div>
      {!p.sent_to_smarttt && p.not_sent_reason && <p className="text-sm text-warning">{p.not_sent_reason}</p>}
      {p.can_send && (
        <button type="button" onClick={onSend} disabled={sending} className={btn.primary}>
          <Send className="size-4" aria-hidden /> {sending ? 'Sending…' : 'Send to SMARTTT now'}
        </button>
      )}
      {printing === 'failed' && <p role="alert" className="text-sm text-danger">Couldn't prepare the timetable to print. Try again, or download the PDF.</p>}
    </li>
  )
}
