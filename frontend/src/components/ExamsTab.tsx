import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import { errorBody, errorMessage } from '@/lib/api'
import { ExamSwitch } from '@/components/ExamSwitch'
import { DirectorPapers } from '@/components/DirectorPapers'
import { dateTime } from '@/lib/format'
import {
  useExamDepartments,
  useExams,
  useImportExams,
  usePatchExamPeriod,
  useRuns,
  useSendExamPublication,
  useSetCurrentTerm,
  useSetPaperCategory,
  useSetPaperRows,
  type PaperRowInput,
  useStartExamRun,
} from '@/lib/queries'
import type { ExamCategory, ExamPaperItem, ExamPeriod, ExamSessionTime } from '@/lib/types'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/**
 * The term's exam timetable: the exam period, the papers departments
 * published (imported from Smart Attendance), generating, drafts and versions.
 */
export function ExamsTab({ termId }: { termId: string }) {
  const exams = useExams(termId)
  const departments = useExamDepartments(termId)
  const importExams = useImportExams(termId)
  const start = useStartExamRun(termId)
  const category = useSetPaperCategory(termId)
  const [numbersOf, setNumbersOf] = useState<string | null>(null)
  const setCurrent = useSetCurrentTerm(termId)
  const send = useSendExamPublication(termId)
  const runs = useRuns(termId)
  const [minutes, setMinutes] = useState(5)

  if (exams.isPending) return <p className="text-sm text-muted">Loading exams…</p>
  if (exams.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(exams.error)}</p>
  const data = exams.data
  const examRuns = (runs.data ?? []).filter((r) => r.mode === 'exam')
  const failure = errorBody(start.error)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <button type="button" disabled={setCurrent.isPending} className="rounded-md border border-line px-3 py-1.5 disabled:opacity-50"
          onClick={() => { if (window.confirm('Make this the current term in SMARTTT? Students and lecturers will see this term from now on.')) setCurrent.mutate() }}>
          Set as current term in SMARTTT
        </button>
        {setCurrent.isSuccess && <span role="status" className="text-muted">This is now SMARTTT's current term, and exam timetables can be sent to it.</span>}
        {setCurrent.isError && <span role="alert" className="text-danger">{errorMessage(setCurrent.error)}</span>}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <PeriodForm termId={termId} period={data.period} />
        <section className="space-y-3 rounded-lg border border-line bg-card p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="font-semibold">Exam papers</h2>
              <p className="text-sm text-muted">Departments list their papers on their Teaching page in Smart Attendance and publish them.</p>
            </div>
            <button onClick={() => importExams.mutate(undefined)} disabled={importExams.isPending}
              className="rounded-md bg-brand px-3 py-2 text-sm text-white disabled:opacity-50">
              {importExams.isPending ? 'Importing…' : 'Import exam papers'}
            </button>
          </div>
          {departments.isError && <p role="alert" className="text-sm text-danger">{errorMessage(departments.error)}</p>}
          {departments.data && (
            <p className="text-sm">
              Published: {departments.data.published.map((d) => `${d.code} (${d.papers})`).join(', ') || 'none yet, so there is nothing to import until a department publishes'}.
              {departments.data.not_published.length > 0 && (
                <span className="text-muted"> Not yet: {departments.data.not_published.map((d) => d.code).join(', ')}.</span>
              )}
            </p>
          )}
          {importExams.isError && <p role="alert" className="text-sm text-danger">{errorMessage(importExams.error)}</p>}
          {importExams.isSuccess && (
            <p role="status" className="text-sm text-success">
              Imported {importExams.data.departments.join(', ')}: {importExams.data.papers.added.length} papers added,{' '}
              {importExams.data.papers.changed.length} changed, {importExams.data.papers.removed.length} removed.
            </p>
          )}
          <p className="text-sm">
            {data.papers.length} papers · {data.papers.reduce((n, p) => n + p.students, 0).toLocaleString()} student entries ·{' '}
            {data.practicals.length} practicals
          </p>
          {data.papers.length > 0 && (
            <details className="text-sm">
              <summary className="cursor-pointer text-brand-ink">Show the papers</summary>
              <ul className="mt-2 max-h-64 overflow-y-auto">
                {data.papers.map((p) => (
                  <li key={p.id} className="border-b border-line py-1 last:border-0">
                    <div className="flex items-center justify-between gap-2">
                    <span><b>{p.codes}</b> {p.title} <span className="text-muted">· {p.department}</span></span>
                    <span className="flex shrink-0 items-center gap-2">
                      <select aria-label={`Category of ${p.codes}`} value={p.category_override ?? ''} className="rounded-md border border-line px-1 py-0.5 text-xs"
                        onChange={(e) => category.mutate({ paperId: p.id, category: (e.target.value || null) as ExamCategory | null })}>
                        <option value="">{`Auto: ${CATEGORY_NAMES[p.category]}`}</option>
                        {(Object.keys(CATEGORY_NAMES) as ExamCategory[]).map((c) => <option key={c} value={c}>{CATEGORY_NAMES[c]}</option>)}
                      </select>
                      <button type="button" className={p.students ? 'text-brand-ink' : 'text-warning'} aria-label={`Students of ${p.codes}: ${p.students}`}
                        onClick={() => setNumbersOf(numbersOf === p.id ? null : p.id)}>{p.students}</button>
                    </span>
                    </div>
                    {numbersOf === p.id && <PaperNumbers termId={termId} paper={p} onClose={() => setNumbersOf(null)} />}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      </div>

      <DirectorPapers termId={termId} papers={data.papers} />

      <section className="space-y-3 rounded-lg border border-line bg-card p-4">
        <h2 className="font-semibold">Generate</h2>
        {data.readiness.length > 0 ? (
          <ul className="list-disc pl-5 text-sm text-warning">{data.readiness.map((r) => <li key={r.code}>{r.message}</li>)}</ul>
        ) : (
          <div className="flex flex-wrap items-end gap-3 text-sm">
            <label>Time limit (minutes)
              <input type="number" min={1} max={60} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}
                className="mt-1 block w-24 rounded-md border border-line px-2 py-1" />
            </label>
            <button onClick={() => start.mutate(minutes * 60)} disabled={start.isPending}
              className="rounded-md bg-brand px-4 py-2 font-medium text-white disabled:opacity-50">
              {start.isPending ? 'Generating…' : 'Generate the exam timetable'}
            </button>
          </div>
        )}
        {failure && <p role="alert" className="text-sm text-danger">{failure.message}</p>}
        <ul className="space-y-2">
          {examRuns.slice(0, 5).map((r) => (
            <li key={r.id} className="rounded-md border border-line p-2 text-sm">
              <div className="flex flex-wrap justify-between gap-2">
                <span>Started {dateTime(r.created_at)} by {r.created_by}</span>
                <span className={clsx('rounded px-2 py-0.5 text-xs font-medium',
                  r.status === 'succeeded' ? 'bg-success-soft text-success' : r.status === 'failed' ? 'bg-danger-soft text-danger' : 'bg-brand-soft text-brand-ink')}>
                  {r.status}
                </span>
              </div>
              {r.status === 'succeeded' && r.draft_id && (
                <p className="mt-1">
                  Back-to-back: {r.soft_scores.back_to_back ?? 0} · Two a day: {r.soft_scores.same_day ?? 0}
                  {r.soft_scores.postgraduate_extra_rooms ? ` · Postgraduate extra rooms: ${r.soft_scores.postgraduate_extra_rooms}` : ''}{' '}
                  <Link to={`/terms/${termId}/exam-drafts/${r.draft_id}`} className="text-brand-ink">Review the draft →</Link>
                </p>
              )}
              {r.failure && <ul className="mt-1 list-disc pl-5 text-danger">{r.failure.reasons.slice(0, 8).map((x, i) => <li key={i}>{x.message}</li>)}</ul>}
            </li>
          ))}
        </ul>
      </section>

      {data.publications.length > 0 && <ExamSwitch termId={termId} />}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-line bg-card p-4">
          <h2 className="mb-2 font-semibold">Exam drafts</h2>
          <ul className="space-y-1 text-sm">
            {data.drafts.map((d) => (
              <li key={d.id} className="flex justify-between gap-2">
                <Link to={`/terms/${termId}/exam-drafts/${d.id}`} className="text-brand-ink">{d.name}</Link>
                <span className="text-muted">{d.status}{d.shared_at ? ' · shared' : ''} · {dateTime(d.created_at)}</span>
              </li>
            ))}
            {data.drafts.length === 0 && <li className="text-muted">None yet.</li>}
          </ul>
        </section>
        <section className="rounded-lg border border-line bg-card p-4">
          <h2 className="mb-2 font-semibold">Published exam versions</h2>
          <ul className="space-y-1 text-sm">
            {data.publications.map((p) => (
              <li key={p.version}>
                <Link to={`/terms/${termId}/exam-drafts/${p.draft_id}`} className="font-medium text-brand-ink">Version {p.version}</Link>
                {' '}· {dateTime(p.published_at)} by {p.published_by}
                {!p.sent_to_smarttt && <span className="block text-warning">Approved here, not yet in SMARTTT{p.not_sent_reason ? `: ${p.not_sent_reason}` : ''}</span>}
                {p.can_send && (
                  <button onClick={() => send.mutate(p.version)} disabled={send.isPending}
                    className="mt-1 rounded-md border border-warning/40 bg-warning-soft px-2 py-1 text-warning disabled:opacity-50">
                    {send.isPending ? 'Sending…' : 'Send to SMARTTT now'}
                  </button>
                )}
              </li>
            ))}
            {data.publications.length === 0 && <li className="text-muted">Nothing published yet.</li>}
            {send.isError && <li role="alert" className="text-danger">{errorMessage(send.error)}</li>}
          </ul>
          {send.isError && <p role="alert" className="mt-2 text-sm text-danger">{errorMessage(send.error)}</p>}
        </section>
      </div>
    </div>
  )
}

/** Numbers and classes the Director enters on a paper. A number from the department replaces them on import. */
function PaperNumbers({ termId, paper, onClose }: { termId: string; paper: ExamPaperItem; onClose: () => void }) {
  const save = useSetPaperRows(termId)
  const [rows, setRows] = useState<PaperRowInput[]>(paper.rows.map(({ programme, year, semester, stream, students }) => ({ programme, year, semester, stream, students })))
  const set = (i: number, patch: Partial<PaperRowInput>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const input = 'rounded-md border border-line px-2 py-1'
  return (
    <div className="mt-2 space-y-2 rounded-md border border-line p-3">
      <h3 className="font-semibold">Students sitting {paper.codes}</h3>
      <p className="text-xs text-muted">For classes with no number. These stay when you import again, until the department sends a number for that class. Seats change on the next draft.</p>
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2">
          <input aria-label="Programme" placeholder="Programme" value={r.programme} onChange={(e) => set(i, { programme: e.target.value })} className={`${input} w-32`} />
          <label>Year <input aria-label="Year" type="number" min={1} max={10} value={r.year} onChange={(e) => set(i, { year: Number(e.target.value) })} className={`${input} w-14`} /></label>
          <label>Sem <input aria-label="Semester" type="number" min={1} max={3} value={r.semester} onChange={(e) => set(i, { semester: Number(e.target.value) })} className={`${input} w-14`} /></label>
          <input aria-label="Stream" placeholder="Stream" value={r.stream} onChange={(e) => set(i, { stream: e.target.value })} className={`${input} w-20`} />
          <label>Students <input aria-label="Students" type="number" min={0} max={5000} value={r.students} onChange={(e) => set(i, { students: Number(e.target.value) })} className={`${input} w-20`} /></label>
          <button type="button" className="text-danger" onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      {rows.length === 0 && <p className="text-muted">No class yet. Add the classes that sit it.</p>}
      {save.isError && <p role="alert" className="text-danger">{errorMessage(save.error)}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="button" className="rounded-md border border-line px-3 py-1" onClick={() => setRows([...rows, { programme: '', year: 1, semester: 1, stream: '', students: 0 }])}>Add a class</button>
        <button type="button" disabled={save.isPending} className="rounded-md bg-brand px-3 py-1 text-white disabled:opacity-50"
          onClick={() => save.mutate({ paperId: paper.id, rows: rows.filter((r) => r.programme.trim()) }, { onSuccess: onClose })}>Save</button>
        <button type="button" className="rounded-md border border-line px-3 py-1" onClick={onClose}>Cancel</button>
      </div>
    </div>
  )
}

const CATEGORY_NAMES: Record<ExamCategory, string> = { regular: 'Regular', common: 'Common', postgraduate: 'Postgraduate' }

function PeriodForm({ termId, period }: { termId: string; period: ExamPeriod }) {
  const save = usePatchExamPeriod(termId)
  const [start, setStart] = useState(period.exam_start ?? '')
  const [end, setEnd] = useState(period.exam_end ?? '')
  const [weekdays, setWeekdays] = useState(period.exam_weekdays)
  const [daysOff, setDaysOff] = useState(period.exam_days_off.join(', '))
  const [sessions, setSessions] = useState<ExamSessionTime[]>(period.exam_sessions)
  const [spacing, setSpacing] = useState(period.exam_spacing)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({
      exam_start: start || null,
      exam_end: end || null,
      exam_weekdays: weekdays,
      exam_days_off: daysOff.split(/[,\s]+/).filter(Boolean),
      exam_sessions: sessions,
      exam_spacing: spacing,
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-card p-4 text-sm">
      <h2 className="font-semibold">Exam period</h2>
      <div className="grid grid-cols-2 gap-3">
        <label>First day<input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="mt-1 block w-full rounded-md border border-line px-2 py-1" /></label>
        <label>Last day<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="mt-1 block w-full rounded-md border border-line px-2 py-1" /></label>
      </div>
      <fieldset className="flex flex-wrap gap-3">
        <legend className="mb-1">Weekdays used</legend>
        {WEEKDAYS.map((d, i) => (
          <label key={d} className="flex items-center gap-1">
            <input type="checkbox" checked={weekdays.includes(i)}
              onChange={(e) => setWeekdays(e.target.checked ? [...weekdays, i].sort() : weekdays.filter((w) => w !== i))} /> {d}
          </label>
        ))}
      </fieldset>
      <label className="block">Days off (public holidays), as 2026-12-12, separated by commas
        <input value={daysOff} onChange={(e) => setDaysOff(e.target.value)} className="mt-1 block w-full rounded-md border border-line px-2 py-1" />
      </label>
      <fieldset>
        <legend className="mb-1">Sessions each day</legend>
        {sessions.map((s, i) => (
          <div key={i} className="mb-1 flex items-center gap-2">
            <input type="time" value={s.start} aria-label={`Session ${i + 1} start`}
              onChange={(e) => setSessions(sessions.map((x, j) => (j === i ? { ...x, start: e.target.value } : x)))} className="rounded-md border border-line px-2 py-1" />
            to
            <input type="time" value={s.end} aria-label={`Session ${i + 1} end`}
              onChange={(e) => setSessions(sessions.map((x, j) => (j === i ? { ...x, end: e.target.value } : x)))} className="rounded-md border border-line px-2 py-1" />
            {sessions.length > 1 && <button type="button" onClick={() => setSessions(sessions.filter((_, j) => j !== i))} className="text-danger">Remove</button>}
          </div>
        ))}
        {sessions.length < 6 && (
          <button type="button" onClick={() => setSessions([...sessions, { start: '17:00', end: '19:00' }])} className="text-brand-ink">+ A session</button>
        )}
      </fieldset>
      <label className="block">Exam seats, as a share of each room's capacity (spacing)
        <input type="number" min={0.3} max={1} step={0.05} value={spacing} onChange={(e) => setSpacing(Number(e.target.value))}
          className="mt-1 block w-28 rounded-md border border-line px-2 py-1" />
      </label>
      <p className="text-xs text-muted">
        Common and postgraduate (7xx to 9xx) papers sit only in the first or last session of a day. A paper of over 3000 students counts as common, and sits first or last whenever it can.
        Postgraduate papers also sit only in the first week: from the first exam day to that week's Friday.
      </p>
      <p className="text-muted">
        {period.days.length} exam days · {period.slots} sessions · {period.rooms} rooms with {period.exam_seats.toLocaleString()} exam seats.
        A room's own exam seats are set on the Rooms page.
      </p>
      {save.isError && <p role="alert" className="text-danger">{errorMessage(save.error)}</p>}
      <button type="submit" disabled={save.isPending} className="rounded-md bg-brand px-4 py-2 text-white disabled:opacity-50">Save the period</button>
    </form>
  )
}
