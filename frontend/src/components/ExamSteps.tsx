import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import { AlertTriangle, ArrowRight, Check, Download, FileText, FileUp, Play, Send } from 'lucide-react'
import { errorBody, errorMessage } from '@/lib/api'
import { ExamSwitch } from '@/components/ExamSwitch'
import { DirectorPapers } from '@/components/DirectorPapers'
import { ExamLetterUpload } from '@/components/ExamLetterUpload'
import { Card, IconBox, Notice, PanelButton, Pill, btn, type Tone } from '@/components/ui'
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
import type { ExamCategory, ExamOverview, ExamPaperItem, ExamPeriod, ExamSessionTime, Run } from '@/lib/types'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/*
 * The term's exam timetable in four steps (TermPage, ?mode=exams): the exam period, the papers
 * departments published (imported from Smart Attendance), generating, and drafts and versions.
 */

function useExamData(termId: string): { data?: ExamOverview; status?: React.ReactNode } {
  const exams = useExams(termId)
  if (exams.isPending) return { status: <p className="text-sm text-muted">Loading exams…</p> }
  if (exams.isError) return { status: <p role="alert" className="text-sm text-danger">{errorMessage(exams.error)}</p> }
  return { data: exams.data }
}

const day = (d: string | null) => (d ? new Date(`${d}T00:00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) : '—')

export function ExamPeriodStep({ termId }: { termId: string }) {
  const { data, status } = useExamData(termId)
  const setCurrent = useSetCurrentTerm(termId)
  if (!data) return status
  const p = data.period
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Exam period">
        <dl className="grid grid-cols-2 gap-4 text-[15px]">
          <div><dt className="text-sm text-muted">First day</dt><dd className="mt-0.5">{day(p.exam_start)}</dd></div>
          <div><dt className="text-sm text-muted">Last day</dt><dd className="mt-0.5">{day(p.exam_end)}</dd></div>
          <div><dt className="text-sm text-muted">Weekdays</dt><dd className="mt-0.5">{p.exam_weekdays.map((w) => WEEKDAYS[w]).join(', ') || '—'}</dd></div>
          <div><dt className="text-sm text-muted">Sessions a day</dt><dd className="mt-0.5">{p.exam_sessions.map((s) => s.start).join(' · ')}</dd></div>
        </dl>
        <p className="text-sm text-muted">{p.days.length} exam days · {p.slots} sessions · {p.rooms} rooms with {p.exam_seats.toLocaleString()} exam seats</p>
        <PanelButton label="Change the period" title="Exam period" className={btn.primary}>
          <PeriodForm termId={termId} period={p} />
        </PanelButton>
      </Card>
      <Card title="SMARTTT's current term">
        <p className="text-sm text-muted">Exam timetables are sent to SMARTTT's current term. Students and lecturers see that term.</p>
        <button type="button" disabled={setCurrent.isPending} className={btn.secondary}
          onClick={() => { if (window.confirm('Make this the current term in SMARTTT? Students and lecturers will see this term from now on.')) setCurrent.mutate() }}>
          Set as current term in SMARTTT
        </button>
        {setCurrent.isSuccess && <p role="status" className="text-sm text-success">This is now SMARTTT's current term, and exam timetables can be sent to it.</p>}
        {setCurrent.isError && <p role="alert" className="text-sm text-danger">{errorMessage(setCurrent.error)}</p>}
      </Card>
    </div>
  )
}

export function ExamPapersStep({ termId }: { termId: string }) {
  const { data, status } = useExamData(termId)
  const departments = useExamDepartments(termId)
  const importExams = useImportExams(termId)
  if (!data) return status
  const mine = data.papers.filter((p) => p.director_paper).length
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center gap-8">
          <div className="min-w-0 flex-1 basis-80 space-y-3">
            <h2 className="text-lg font-semibold">Exam papers</h2>
            <p className="flex flex-wrap items-baseline gap-2">
              <span className="text-5xl font-bold tracking-tight text-brand-ink">{data.papers.length}</span>
              <span className="text-lg text-muted">papers · {data.papers.reduce((n, p) => n + p.students, 0).toLocaleString()} student entries · {data.practicals.length} practicals</span>
            </p>
            {departments.data && (
              <p className="text-sm text-muted">
                {departments.data.published.length} departments have published their papers
                {departments.data.not_published.length > 0 && `; not yet: ${departments.data.not_published.map((d) => d.code).join(', ')}`}.
              </p>
            )}
            {departments.isError && <p role="alert" className="text-sm text-danger">{errorMessage(departments.error)}</p>}
            <p className="text-sm text-muted">Departments upload their moderation letters in Smart Attendance and publish them. You can upload a department's letter here too.</p>
          </div>
          <div className="flex flex-1 basis-56 flex-col gap-2 sm:max-w-xs">
            <button type="button" onClick={() => importExams.mutate(undefined)} disabled={importExams.isPending} className={clsx(btn.primary, 'py-3 text-base')}>
              <Download className="size-5" aria-hidden /> {importExams.isPending ? 'Importing…' : 'Import exam papers'}
            </button>
            <PanelButton label="Upload a moderation letter" title="Upload a department's moderation letter" wide icon={FileUp}>
              {(close) => <ExamLetterUpload termId={termId} onDone={close} />}
            </PanelButton>
            {data.papers.length > 0 && (
              <PanelButton label="Show the papers" title="Exam papers" wide><PaperList termId={termId} papers={data.papers} /></PanelButton>
            )}
            {mine > 0 && (
              <PanelButton label={`Papers you uploaded earlier (${mine})`} title="Papers you uploaded earlier" wide className={btn.quiet}>
                <DirectorPapers termId={termId} papers={data.papers} />
              </PanelButton>
            )}
          </div>
        </div>
      </Card>
      {importExams.isError && <p role="alert" className="text-sm text-danger">{errorMessage(importExams.error)}</p>}
      {importExams.isSuccess && (
        <Notice tone="success" icon={Check}>
          Imported {importExams.data.departments.join(', ')}: {importExams.data.papers.added.length} papers added,{' '}
          {importExams.data.papers.changed.length} changed, {importExams.data.papers.removed.length} removed.
        </Notice>
      )}
    </div>
  )
}

function PaperList({ termId, papers }: { termId: string; papers: ExamPaperItem[] }) {
  const category = useSetPaperCategory(termId)
  const [numbersOf, setNumbersOf] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()
  const shown = papers.filter((p) => !q || p.codes.toLowerCase().includes(q) || p.title.toLowerCase().includes(q) || p.department.toLowerCase().includes(q))
  return (
    <div className="space-y-3 text-sm">
      <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search code, title or department"
        aria-label="Search papers" className="w-full rounded-md border border-line px-3 py-2" />
      <p className="text-muted">Click a paper's number of students to enter classes without a number from the department.</p>
      {category.isError && <p role="alert" className="text-danger">{errorMessage(category.error)}</p>}
      <ul className="divide-y divide-line rounded-lg border border-line">
        {shown.map((p) => (
          <li key={p.id} className="px-3 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span><b>{p.codes}</b> {p.title} <span className="text-muted">· {p.department}</span></span>
              <span className="flex shrink-0 items-center gap-2">
                <select aria-label={`Category of ${p.codes}`} value={p.category_override ?? ''} className="rounded-md border border-line px-2 py-1 text-xs"
                  onChange={(e) => category.mutate({ paperId: p.id, category: (e.target.value || null) as ExamCategory | null })}>
                  <option value="">{`Auto: ${CATEGORY_NAMES[p.category]}`}</option>
                  {(Object.keys(CATEGORY_NAMES) as ExamCategory[]).map((c) => <option key={c} value={c}>{CATEGORY_NAMES[c]}</option>)}
                </select>
                <button type="button" className={clsx('min-w-12 rounded-lg px-2 py-1 font-semibold', p.students ? 'bg-brand-soft text-brand-ink' : 'bg-warning-soft text-warning')}
                  aria-label={`Students of ${p.codes}: ${p.students}`} onClick={() => setNumbersOf(numbersOf === p.id ? null : p.id)}>{p.students}</button>
              </span>
            </div>
            {numbersOf === p.id && <PaperNumbers termId={termId} paper={p} onClose={() => setNumbersOf(null)} />}
          </li>
        ))}
        {shown.length === 0 && <li className="px-3 py-4 text-center text-muted">No paper matches.</li>}
      </ul>
    </div>
  )
}

const RUN_TONE: Record<Run['status'], Tone> = { succeeded: 'success', failed: 'danger', running: 'brand', queued: 'brand' }
const RUN_STATUS: Record<Run['status'], string> = { succeeded: 'Finished', failed: 'Failed', running: 'Running', queued: 'Waiting to start' }

function ExamRun({ run, termId }: { run: Run; termId: string }) {
  return (
    <div className="space-y-3 rounded-lg bg-surface p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Pill tone={RUN_TONE[run.status]}>{RUN_STATUS[run.status]}</Pill>
        <span className="text-muted">{dateTime(run.created_at)} by {run.created_by}</span>
      </div>
      {run.status === 'succeeded' && run.draft_id && (
        <>
          <p className="text-muted">
            Back-to-back: {run.soft_scores.back_to_back ?? 0} · Two a day: {run.soft_scores.same_day ?? 0}
            {run.soft_scores.postgraduate_extra_rooms ? ` · Postgraduate extra rooms: ${run.soft_scores.postgraduate_extra_rooms}` : ''}
          </p>
          <Link to={`/terms/${termId}/exam-drafts/${run.draft_id}`} className={btn.primary}>Review the draft <ArrowRight className="size-4" aria-hidden /></Link>
        </>
      )}
      {run.failure && <ul className="list-disc pl-5 text-danger">{run.failure.reasons.slice(0, 8).map((x, i) => <li key={i}>{x.message}</li>)}</ul>}
    </div>
  )
}

export function ExamGenerateStep({ termId }: { termId: string }) {
  const { data, status } = useExamData(termId)
  const start = useStartExamRun(termId)
  const runs = useRuns(termId)
  const [minutes, setMinutes] = useState(5)
  if (!data) return status
  const examRuns = (runs.data ?? []).filter((r) => r.mode === 'exam')
  const failure = errorBody(start.error)
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Generate the exam timetable">
        <p className="text-sm text-muted">Each paper gets a day, a session and rooms. Departments name invigilators once you share the draft.</p>
        {data.readiness.length > 0 ? (
          <Notice icon={AlertTriangle} action={
            <PanelButton label="Show them" title="To fix before generating">
              <ul className="list-disc space-y-1.5 pl-5 text-sm">{data.readiness.map((r) => <li key={r.code}>{r.message}</li>)}</ul>
            </PanelButton>
          }>{data.readiness.length} things to fix first.</Notice>
        ) : (
          <>
            <label className="flex items-center gap-3 text-sm text-muted">Stop after
              <input type="number" min={1} max={60} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}
                aria-label="Time limit in minutes" className="w-20 rounded-md border border-line px-3 py-1.5 text-ink" /> minutes
            </label>
            <button type="button" onClick={() => start.mutate(minutes * 60)} disabled={start.isPending} className={clsx(btn.gold, 'w-full')}>
              <Play className="size-5 fill-current" aria-hidden /> {start.isPending ? 'Generating…' : 'Generate exams'}
            </button>
          </>
        )}
        {failure && <p role="alert" className="text-sm text-danger">{failure.message}</p>}
      </Card>
      <Card title="Last run" action={examRuns.length > 1 && (
        <PanelButton label="All runs" title="Exam runs" className={btn.quiet}>
          <ul className="space-y-3">{examRuns.map((r) => <li key={r.id}><ExamRun run={r} termId={termId} /></li>)}</ul>
        </PanelButton>
      )}>
        {examRuns[0] ? <ExamRun run={examRuns[0]} termId={termId} /> : <p className="text-sm text-muted">No runs yet.</p>}
      </Card>
    </div>
  )
}

export function ExamPublishStep({ termId }: { termId: string }) {
  const { data, status } = useExamData(termId)
  const send = useSendExamPublication(termId)
  if (!data) return status
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Exam drafts">
          <ul className="space-y-2">
            {data.drafts.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-3 rounded-lg bg-surface px-4 py-3">
                <IconBox icon={FileText} />
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold">{d.name}</span>
                  <span className="block text-sm text-muted">{dateTime(d.created_at)}{d.shared_at ? ' · shared with departments' : ''}</span>
                </span>
                <Pill tone={d.status === 'published' ? 'success' : d.status === 'draft' ? 'brand' : 'muted'}>{d.status}</Pill>
                <Link to={`/terms/${termId}/exam-drafts/${d.id}`} className={btn.secondary}>Open</Link>
              </li>
            ))}
            {data.drafts.length === 0 && <li className="text-sm text-muted">None yet. Generate one first.</li>}
          </ul>
        </Card>
        <Card title="Published">
          <ul className="space-y-2">
            {data.publications.map((p, i) => (
              <li key={p.version} className={clsx('space-y-2 rounded-lg px-4 py-3', i === 0 ? 'bg-brand-soft' : 'bg-surface')}>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="min-w-0 flex-1">
                    <Link to={`/terms/${termId}/exam-drafts/${p.draft_id}`} className="block font-semibold text-brand-ink">Version {p.version}</Link>
                    <span className="block text-sm text-muted">{dateTime(p.published_at)} by {p.published_by}</span>
                  </span>
                  {p.sent_to_smarttt ? <Pill tone="success">On SMARTTT</Pill> : <Pill tone="warning">Not in SMARTTT</Pill>}
                </div>
                {!p.sent_to_smarttt && p.not_sent_reason && <p className="text-sm text-warning">{p.not_sent_reason}</p>}
                {p.can_send && (
                  <button type="button" onClick={() => send.mutate(p.version)} disabled={send.isPending} className={btn.primary}>
                    <Send className="size-4" aria-hidden /> {send.isPending ? 'Sending…' : 'Send to SMARTTT now'}
                  </button>
                )}
              </li>
            ))}
            {data.publications.length === 0 && <li className="text-sm text-muted">Nothing published yet. Open a draft and choose Approve and publish.</li>}
          </ul>
          {send.isError && <p role="alert" className="text-sm text-danger">{errorMessage(send.error)}</p>}
        </Card>
      </div>
      {data.publications.length > 0 && <ExamSwitch termId={termId} />}
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
        <button type="button" className={btn.secondary} onClick={() => setRows([...rows, { programme: '', year: 1, semester: 1, stream: '', students: 0 }])}>Add a class</button>
        <button type="button" disabled={save.isPending} className={btn.primary}
          onClick={() => save.mutate({ paperId: paper.id, rows: rows.filter((r) => r.programme.trim()) }, { onSuccess: onClose })}>Save</button>
        <button type="button" className={btn.secondary} onClick={onClose}>Cancel</button>
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
  const [graduateRoom, setGraduateRoom] = useState(period.exam_postgraduate_room ?? '')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({
      exam_start: start || null,
      exam_end: end || null,
      exam_weekdays: weekdays,
      exam_days_off: daysOff.split(/[,\s]+/).filter(Boolean),
      exam_sessions: sessions,
      exam_spacing: spacing,
      exam_postgraduate_room: graduateRoom.trim(),
    })
  }

  return (
    <form onSubmit={submit} className="space-y-4 text-sm">
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
      <label className="block">Postgraduate room
        <input value={graduateRoom} onChange={(e) => setGraduateRoom(e.target.value)} placeholder="TC 1"
          className="mt-1 block w-28 rounded-md border border-line px-2 py-1" />
        <span className="mt-1 block text-xs text-muted">
          A session's postgraduate papers sit here first. When it is full they take other rooms in its building, and undergraduates fill the seats left in those rooms; undergraduates keep out of this room only while postgraduates sit. Leave empty for no postgraduate room. You can still give any paper another venue on the draft.
          {period.exam_postgraduate_room && (period.postgraduate_room
            ? ` Now: ${period.postgraduate_room.code}, ${period.postgraduate_room.seats} exam seats, building ${period.postgraduate_room.building}.`
            : ` No room ${period.exam_postgraduate_room} is open for exams, so postgraduate papers sit in any room.`)}
        </span>
      </label>
      <p className="text-xs text-muted">
        Postgraduate (7xx to 9xx) papers sit only in the first or last session of a day. Common papers sit first or last when they can, and take a middle session when the timetable needs it. A paper of over 3000 students counts as common.
        Postgraduate papers also sit only in the first week: from the first exam day to that week's Friday.
      </p>
      <p className="text-muted">
        {period.days.length} exam days · {period.slots} sessions · {period.rooms} rooms with {period.exam_seats.toLocaleString()} exam seats.
        A room's own exam seats are set on the Rooms page.
      </p>
      {save.isError && <p role="alert" className="text-danger">{errorMessage(save.error)}</p>}
      {save.isSuccess && <p role="status" className="text-success">Saved.</p>}
      <button type="submit" disabled={save.isPending} className={btn.primary}>Save the period</button>
    </form>
  )
}
