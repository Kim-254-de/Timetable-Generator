import { useId, useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Dialog, Field, inputClass } from '@/components/Dialog'
import type { BulkColumn } from '@/components/BulkPaste'
import { errorMessage } from '@/lib/api'
import { termText } from '@/lib/format'
import {
  useCopyTerm,
  useCreateClassRow,
  useCreateOffering,
  useDepartments,
  useEditOffering,
  usePatchRow,
  usePatchTerm,
  useRoomList,
  useTerm,
  useTerms,
  type ClassRowInput,
  type OfferingInput,
} from '@/lib/queries'
import type { ClassRow, Offering, RoomType, Term } from '@/lib/types'
import { ROOM_TYPE_NAMES } from './RoomsPage'

export const CLASS_ROW_COLUMNS: BulkColumn[] = [
  { key: 'programme', label: 'Programme', example: 'BED.BIO/AGR', required: true },
  { key: 'year', label: 'Year', example: '1', required: true },
  { key: 'semester', label: 'Semester', example: '1', required: true, hint: "The student's own semester (the S1 in Y1S1)" },
  { key: 'sub_class', label: 'Sub class', example: '2', hint: 'Blank, or 1, 2, 3… for a cohort printed as several rows, e.g. "(2)"' },
  { key: 'department', label: 'Department', example: 'Education', hint: 'Its name or code, from Departments (Smart Attendance adds new ones).' },
  { key: 'students', label: 'Students', example: '120' },
]

export const UNIT_COLUMNS: BulkColumn[] = [
  { key: 'unit_code', label: 'Unit code', example: 'COSC 103', required: true },
  { key: 'unit_title', label: 'Unit title', example: 'Introduction to ICT Skills', required: true },
  { key: 'department', label: 'Department', example: 'Computer Science', required: true, hint: 'The name or code of the department that owns the unit, from Departments (Smart Attendance adds new ones).' },
  { key: 'hours_per_week', label: 'Hours per week', example: '3', hint: "Blank = the term's class length" },
  { key: 'class_length', label: 'Class length', example: '3', hint: 'Hours per meeting' },
  { key: 'room_type', label: 'Room type', example: 'Lecture hall', hint: 'Lecture hall, Lab or Seminar room. COSC units go to a lab whenever one seats the group' },
  { key: 'class_rows', label: 'Class rows', example: 'BED.BIO/AGR Y1S1 (2); BED.MATH/BIO Y1S1',
    hint: 'The class rows that take the unit, separated by ";" (exactly as on the Class rows tab)' },
]

/** Term details printed on the timetable, plus links to the shared lists. */
export function TermDetails({ termId }: { termId: string }) {
  const term = useTerm(termId)
  const rooms = useRoomList()
  const departments = useDepartments()
  if (!term.data) return null
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <TermDetailsForm term={term.data} key={term.data.id} />
      <section className="space-y-3 rounded-lg border border-line bg-card p-4 text-sm">
        <h2 className="font-semibold">What the Generator needs</h2>
        <ol className="list-decimal space-y-1 pl-5">
          <li><Link to="/rooms" className="text-brand-ink">Lecture halls</Link>: {rooms.data?.length ?? 0} entered (shared by every term)</li>
          <li><Link to="/departments" className="text-brand-ink">Departments</Link>: {departments.data?.length ?? 0} entered (shared by every term)</li>
          <li><Link to={`/terms/${termId}?tab=rows`} className="text-brand-ink">Class rows</Link>: the cohorts printed on the timetable, with student numbers</li>
          <li><Link to={`/terms/${termId}?tab=units`} className="text-brand-ink">Units and groups</Link>: each unit, the class rows that take it, and how it is split into groups</li>
          <li><Link to={`/terms/${termId}?tab=runs`} className="text-brand-ink">Generate</Link>, review, approve and download</li>
        </ol>
        <CopyFromTerm termId={termId} />
      </section>
    </div>
  )
}

function TermDetailsForm({ term }: { term: Term }) {
  const patch = usePatchTerm(term.id)
  const [form, setForm] = useState({
    name: term.name,
    start_date: term.start_date ?? '',
    end_date: term.end_date ?? '',
    version_label: term.version_label,
    use_from: term.use_from ?? '',
    prepared_by: term.prepared_by,
    prepared_by_title: term.prepared_by_title,
    default_session_length: term.default_session_length,
  })
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    patch.mutate({
      ...form,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      use_from: form.use_from || null,
      default_session_length: Number(form.default_session_length),
    })
  }
  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-card p-4">
      <h2 className="font-semibold">Term details <span className="font-normal text-muted">· {termText(term)}</span></h2>
      <p className="text-sm text-muted">Printed on the downloaded timetable.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name" hint="e.g. September-December 2026"><input value={form.name} onChange={set('name')} className={inputClass} /></Field>
        <Field label="Class length (hours)" hint="Used for units without their own">
          <input type="number" min={1} max={6} value={form.default_session_length} onChange={set('default_session_length')} className={inputClass} />
        </Field>
        <Field label="Start date"><input type="date" value={form.start_date} onChange={set('start_date')} className={inputClass} /></Field>
        <Field label="End date"><input type="date" value={form.end_date} onChange={set('end_date')} className={inputClass} /></Field>
        <Field label="Version line" hint='e.g. "VERSION_2 DATED 19/09/2026"'><input value={form.version_label} onChange={set('version_label')} className={inputClass} /></Field>
        <Field label="To be used from"><input type="date" value={form.use_from} onChange={set('use_from')} className={inputClass} /></Field>
        <Field label="Prepared by"><input value={form.prepared_by} onChange={set('prepared_by')} placeholder="Dr. …" className={inputClass} /></Field>
        <Field label="Title"><input value={form.prepared_by_title} onChange={set('prepared_by_title')} className={inputClass} /></Field>
      </div>
      {patch.isError && <p role="alert" className="text-sm text-danger">{errorMessage(patch.error)}</p>}
      {patch.isSuccess && <p className="text-sm text-success">Saved.</p>}
      <button type="submit" disabled={patch.isPending} className="rounded-md bg-brand px-4 py-2 text-sm text-white disabled:opacity-50">Save details</button>
    </form>
  )
}

function CopyFromTerm({ termId }: { termId: string }) {
  const terms = useTerms()
  const copy = useCopyTerm(termId)
  const [source, setSource] = useState('')
  const others = (terms.data ?? []).filter((t) => t.id !== termId)
  if (!others.length) return null
  return (
    <div className="border-t border-line pt-3">
      <p className="font-medium">Start from a previous term</p>
      <p className="text-muted">Copies its class rows, units and groups. Anything already here is kept.</p>
      <div className="mt-2 flex gap-2">
        <select value={source} onChange={(e) => setSource(e.target.value)} className="rounded-md border border-line px-2 py-1">
          <option value="">Choose a term…</option>
          {others.map((t) => <option key={t.id} value={t.id}>{t.name || termText(t)}</option>)}
        </select>
        <button disabled={!source || copy.isPending} onClick={() => copy.mutate(source)}
          className="rounded-md border border-line px-3 py-1 disabled:opacity-50">Copy</button>
      </div>
      {copy.isSuccess && <p className="mt-1 text-success">Copied {copy.data.class_rows_copied} class rows and {copy.data.units_copied} units.</p>}
      {copy.isError && <p role="alert" className="mt-1 text-danger">{errorMessage(copy.error)}</p>}
    </div>
  )
}

/** A free-text department name, suggesting the departments already entered. */
function DepartmentInput({ value, onChange, required }: { value: string; onChange: (value: string) => void; required?: boolean }) {
  const departments = useDepartments()
  const listId = useId()
  return (
    <>
      <input required={required} value={value} maxLength={255} list={listId} placeholder="e.g. Computer Science"
        onChange={(e) => onChange(e.target.value)} className={inputClass} />
      <datalist id={listId}>
        {departments.data?.map((d) => <option key={d.id} value={d.name}>{d.code}</option>)}
      </datalist>
    </>
  )
}

export function ClassRowForm({ termId, row, onClose }: { termId: string; row: ClassRow | null; onClose: () => void }) {
  const departments = useDepartments()
  const create = useCreateClassRow(termId)
  const edit = usePatchRow(termId)
  const [form, setForm] = useState<ClassRowInput>({
    program_code: row?.program_code ?? '',
    study_year: row?.study_year ?? 1,
    study_semester: row?.study_semester ?? 1,
    sub_class: row?.sub_class ?? '',
    department: departments.data?.find((d) => d.id === row?.department_id)?.name ?? '',
    student_count: row?.student_count ?? null,
  })
  const failure = create.error ?? edit.error
  const label = `${form.program_code || 'PROGRAMME'} Y${form.study_year}S${form.study_semester}${form.sub_class ? ` (${form.sub_class})` : ''}`
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const body = { ...form, department: form.department?.trim() || undefined }
    if (row) edit.mutate({ id: row.id, body }, { onSuccess: onClose })
    else create.mutate(body, { onSuccess: onClose })
  }
  return (
    <Dialog title={row ? `Edit ${row.label}` : 'Add a class row'} onClose={onClose}>
      <form onSubmit={submit} className="mt-3 space-y-3">
        <p className="text-sm text-muted">Shown on the timetable as <b>{label}</b>.</p>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Field label="Programme" hint="As printed on the timetable, e.g. BED.BIO/AGR or B.LAW">
              <input required value={form.program_code} onChange={(e) => setForm({ ...form, program_code: e.target.value })} className={inputClass} />
            </Field>
          </div>
          <Field label="Year of study">
            <input required type="number" min={1} max={7} value={form.study_year} onChange={(e) => setForm({ ...form, study_year: Number(e.target.value) })} className={inputClass} />
          </Field>
          <Field label="Semester of study" hint="The S1 in Y1S1">
            <input required type="number" min={1} max={3} value={form.study_semester} onChange={(e) => setForm({ ...form, study_semester: Number(e.target.value) })} className={inputClass} />
          </Field>
          <Field label="Sub class" hint="Blank, or 1, 2, 3… when a cohort is split into rows">
            <input value={form.sub_class} maxLength={10} onChange={(e) => setForm({ ...form, sub_class: e.target.value })} className={inputClass} />
          </Field>
          <Field label="Number of students">
            <input type="number" min={0} value={form.student_count ?? ''} onChange={(e) => setForm({ ...form, student_count: e.target.value === '' ? null : Number(e.target.value) })} className={inputClass} />
          </Field>
          <div className="col-span-2">
            <Field label="Department" hint="Type its name or code, from Departments. New departments are added in Smart Attendance.">
              <DepartmentInput value={form.department ?? ''} onChange={(department) => setForm({ ...form, department })} />
            </Field>
          </div>
        </div>
        {failure && <p role="alert" className="text-sm text-danger">{errorMessage(failure)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-2 text-sm">Cancel</button>
          <button type="submit" disabled={create.isPending || edit.isPending} className="rounded-md bg-brand px-4 py-2 text-sm text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </Dialog>
  )
}

export function OfferingForm({
  termId,
  offering,
  rows,
  onClose,
}: {
  termId: string
  offering: Offering | null
  rows: ClassRow[]
  onClose: () => void
}) {
  const departments = useDepartments()
  const term = useTerm(termId)
  const create = useCreateOffering(termId)
  const edit = useEditOffering(termId)
  const length = term.data?.default_session_length ?? 3
  const [form, setForm] = useState<OfferingInput>({
    unit_code: offering?.unit_code ?? '',
    unit_name: offering?.unit_name ?? '',
    department: departments.data?.find((d) => d.id === offering?.department_id)?.name ?? '',
    weekly_hours: offering?.weekly_hours ?? length,
    session_length: offering?.session_length ?? length,
    room_type: offering?.room_type ?? 'lecture_hall',
    class_row_ids: offering?.class_row_ids ?? [],
  })
  const [query, setQuery] = useState('')
  const chosen = new Set(form.class_row_ids)
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter((r) => chosen.has(r.id) || !q || r.label.toLowerCase().includes(q))
  }, [rows, query, form.class_row_ids]) // eslint-disable-line react-hooks/exhaustive-deps
  const students = rows.filter((r) => chosen.has(r.id)).reduce((n, r) => n + (r.student_count ?? 0), 0)
  const failure = create.error ?? edit.error
  const toggle = (id: string) =>
    setForm({ ...form, class_row_ids: chosen.has(id) ? form.class_row_ids?.filter((x) => x !== id) : [...(form.class_row_ids ?? []), id] })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const body = { ...form, department: form.department?.trim() || undefined }
    if (offering) edit.mutate({ id: offering.id, body }, { onSuccess: onClose })
    else create.mutate(body, { onSuccess: onClose })
  }
  return (
    <Dialog title={offering ? `Edit ${offering.unit_code}` : 'Add a unit'} onClose={onClose} wide>
      <form onSubmit={submit} className="mt-3 space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Unit code"><input required value={form.unit_code} onChange={(e) => setForm({ ...form, unit_code: e.target.value })} placeholder="COSC 103" className={inputClass} /></Field>
          <div className="sm:col-span-2">
            <Field label="Unit title"><input required value={form.unit_name} onChange={(e) => setForm({ ...form, unit_name: e.target.value })} className={inputClass} /></Field>
          </div>
          <Field label="Department that owns it" hint="It allocates the lecturer. Type its name or code, from Departments; new ones are added in Smart Attendance.">
            <DepartmentInput required value={form.department ?? ''} onChange={(department) => setForm({ ...form, department })} />
          </Field>
          <Field label="Hours per week">
            <input type="number" min={1} max={20} value={form.weekly_hours} onChange={(e) => setForm({ ...form, weekly_hours: Number(e.target.value) })} className={inputClass} />
          </Field>
          <Field label="Class length (hours)">
            <input type="number" min={1} max={6} value={form.session_length} onChange={(e) => setForm({ ...form, session_length: Number(e.target.value) })} className={inputClass} />
          </Field>
          <Field label="Room type" hint={/^\s*cosc/i.test(form.unit_code ?? '') ? 'COSC units go to a lab whenever one seats the group; only a group too big for every lab uses this type.' : undefined}>
            <select value={form.room_type} onChange={(e) => setForm({ ...form, room_type: e.target.value as RoomType })} className={inputClass}>
              {Object.entries(ROOM_TYPE_NAMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
        </div>
        <div>
          <div className="flex flex-wrap items-end justify-between gap-2">
            <p className="text-sm font-medium text-ink">Class rows taking this unit · {chosen.size} chosen, {students} students</p>
            <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search class rows"
              className="w-60 rounded-md border border-line px-2 py-1 text-sm" />
          </div>
          <div className="mt-2 grid max-h-64 gap-1 overflow-y-auto rounded-md border border-line p-2 text-sm sm:grid-cols-2">
            {shown.map((r) => (
              <label key={r.id} className="flex items-center gap-2">
                <input type="checkbox" checked={chosen.has(r.id)} onChange={() => toggle(r.id)} />
                <span className="flex-1">{r.label}</span>
                <span className="text-muted">{r.student_count ?? '?'}</span>
              </label>
            ))}
            {rows.length === 0 && <p className="text-muted">Add class rows first (Class rows tab).</p>}
          </div>
          <p className="mt-1 text-xs text-muted">A new unit starts as one whole class. Split it into groups (GR A, GR B…) from the Groups column.</p>
        </div>
        {failure && <p role="alert" className="text-sm text-danger">{errorMessage(failure)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-2 text-sm">Cancel</button>
          <button type="submit" disabled={create.isPending || edit.isPending} className="rounded-md bg-brand px-4 py-2 text-sm text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </Dialog>
  )
}
