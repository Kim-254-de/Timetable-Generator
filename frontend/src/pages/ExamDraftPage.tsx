import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import clsx from 'clsx'
import { Download } from 'lucide-react'
import { errorMessage } from '@/lib/api'
import { dateTime } from '@/lib/format'
import { examExportUrl, useExamDraft, useExamDraftAction, useMoveExamPaper } from '@/lib/queries'
import type { ExamGrid, ExamGridPaper } from '@/lib/types'

const roomsOf = (p: ExamGridPaper) => [...new Set(p.seating.map((s) => s.room))].sort()

/**
 * An exam draft as the Director reviews it: the date x session grid of
 * `paper -> rooms` (like the printed timetable), or the room sheets. A paper
 * can be moved (checked); the draft is shared with departments for
 * invigilators, then published.
 */
export function ExamDraftPage() {
  const { termId = '', draftId = '' } = useParams()
  const navigate = useNavigate()
  const grid = useExamDraft(draftId)
  const act = useExamDraftAction(termId, draftId)
  const [view, setView] = useState<'grid' | 'rooms'>('grid')
  const [moving, setMoving] = useState<ExamGridPaper | null>(null)
  const [search, setSearch] = useState('')

  if (grid.isPending) return <p className="text-sm text-muted">Loading the exam draft…</p>
  if (grid.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(grid.error)}</p>
  const data = grid.data
  const draft = data.draft
  const editable = draft.status === 'draft'
  const flagged = new Set(draft.violations.flatMap((v) => v.paper_ids))
  const unnamed = data.papers.reduce((n, p) => n + (p.invigilators[''] ? 0 : 1) + p.extra_rooms.filter((r) => !p.invigilators[r]).length, 0)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to={`/terms/${termId}?tab=exams`} className="text-sm text-brand-ink">← Back to the term</Link>
          <h1 className="text-xl font-semibold">{draft.name}{data.version ? ` · version ${data.version}` : ''}</h1>
          <p className="text-sm text-muted">
            {draft.placed} of {draft.papers} papers placed · {draft.pinned} pinned · <span className="capitalize">{draft.status}</span>
            {draft.shared_at && ` · shared with departments ${dateTime(draft.shared_at)}`}
            {' '}· back-to-back {draft.soft_scores.back_to_back ?? 0} · two a day {draft.soft_scores.same_day ?? 0}
            {draft.soft_scores.common_elsewhere ? ` · ${draft.soft_scores.common_elsewhere} common units not on day 2` : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {(['timetable', 'rooms', 'roster'] as const).map((kind) => (
            <span key={kind} className="inline-flex items-center gap-1 rounded-md border border-line bg-card px-2 py-1">
              <Download size={14} aria-hidden />
              {kind === 'timetable' ? 'Timetable' : kind === 'rooms' ? 'Room sheets' : 'Roster'}:
              <a href={examExportUrl(draftId, kind, 'docx')} className="text-brand-ink">Word</a>
              <a href={examExportUrl(draftId, kind, 'pdf')} className="text-brand-ink">PDF</a>
            </span>
          ))}
          {editable ? (
            <>
              <button onClick={() => act.mutate('resolve', { onSuccess: () => navigate(`/terms/${termId}?tab=exams`) })} disabled={act.isPending}
                className="rounded-md border border-line bg-card px-3 py-2">Re-solve around pins</button>
              <button onClick={() => act.mutate('share')} disabled={act.isPending} className="rounded-md border border-line bg-card px-3 py-2">
                {draft.shared_at ? 'Share again' : 'Share with departments'}
              </button>
              <button onClick={() => act.mutate('publish')} disabled={act.isPending || !draft.publishable}
                title={draft.publishable ? 'Approve and publish (every paper needs an invigilator)' : 'Fix the hard-rule problems first'}
                className="rounded-md bg-brand px-4 py-2 font-medium text-white disabled:opacity-50">Approve and publish</button>
            </>
          ) : (
            <button onClick={() => act.mutate('copy', { onSuccess: (d) => navigate(`/terms/${termId}/exam-drafts/${d.id}`) })}
              className="rounded-md border border-line bg-card px-3 py-2">Copy to a new draft</button>
          )}
        </div>
      </div>

      {act.isError && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{errorMessage(act.error)}</p>}
      {act.isSuccess && act.variables === 'publish' && (
        act.data.smarttt?.sent
          ? <p role="status" className="rounded-md bg-success-soft px-3 py-2 text-sm text-success">Approved as version {act.data.version} and sent to SMARTTT: students see their exams in the app.</p>
          : <p role="status" className="rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">Approved as version {act.data.version}, not yet in SMARTTT{act.data.smarttt?.reason ? `: ${act.data.smarttt.reason}` : ''}. Send it from the Exams tab.</p>
      )}
      {editable && draft.shared_at && unnamed > 0 && (
        <p className="rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">{unnamed} invigilators (main, or for an extra room) are still to be published by departments.</p>
      )}
      {draft.violations.length > 0 && (
        <ul className="list-disc rounded-md bg-danger-soft py-2 pl-8 pr-3 text-sm text-danger">
          {draft.violations.slice(0, 10).map((v, i) => <li key={i}>{v.message}</li>)}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {(['grid', 'rooms'] as const).map((v) => (
          <button key={v} onClick={() => setView(v)}
            className={clsx('rounded-full px-3 py-1 text-sm', view === v ? 'bg-brand text-white' : 'border border-line bg-card')}>
            {v === 'grid' ? 'Date × session' : 'Room sheets'}
          </button>
        ))}
        <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find a paper or room"
          className="ml-auto w-64 rounded-md border border-line px-3 py-1.5 text-sm" />
      </div>

      {view === 'grid'
        ? <Grid data={data} search={search} flagged={flagged} onPick={editable ? setMoving : undefined} />
        : <RoomSheets data={data} search={search} />}

      {data.practicals.length > 0 && (
        <section className="rounded-lg border border-line bg-card p-3 text-sm">
          <h2 className="font-semibold">Practicals (on their departments' dates)</h2>
          <ul className="mt-1">
            {data.practicals.map((p, i) => <li key={i}>{p.date} {p.start_time}–{p.end_time} · {p.codes} {p.title} · {p.department}</li>)}
          </ul>
        </section>
      )}
      {moving && <MoveDialog termId={termId} draftId={draftId} data={data} paper={moving} onClose={() => setMoving(null)} />}
    </div>
  )
}

function Grid({ data, search, flagged, onPick }: {
  data: ExamGrid; search: string; flagged: Set<string>; onPick?: (p: ExamGridPaper) => void
}) {
  const q = search.trim().toLowerCase()
  const cell = (day: string, session: number) =>
    data.papers
      .filter((p) => p.day === day && p.session === session)
      .filter((p) => !q || p.codes.toLowerCase().includes(q) || roomsOf(p).some((r) => r.toLowerCase().includes(q)))
      .sort((a, b) => a.codes.localeCompare(b.codes))
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-card">
      <table className="w-full text-left text-xs">
        <thead className="bg-surface uppercase text-muted">
          <tr>
            <th className="px-2 py-2">Date/day</th>
            {data.sessions.map((s) => <th key={s.start} className="px-2 py-2">{s.start}–{s.end}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.days.map((d) => (
            <tr key={d.date} className="border-t border-line align-top">
              <th className="px-2 py-2 whitespace-nowrap">{d.label}</th>
              {data.sessions.map((s, i) => (
                <td key={s.start} className="px-2 py-2">
                  {cell(d.date, i).map((p) => (
                    <button key={p.id} type="button" disabled={!onPick} onClick={() => onPick?.(p)}
                      title={`${p.title} · ${p.students} students${p.pinned ? ' · pinned' : ''}`}
                      className={clsx('mb-1 block w-full rounded border px-1.5 py-1 text-left',
                        flagged.has(p.id) ? 'border-danger/40 bg-danger-soft' : 'border-line bg-surface', onPick && 'hover:border-brand')}>
                      <b>{p.codes}</b> → {roomsOf(p).join(', ') || 'room to be announced (no students known)'}
                      <span className="block text-muted">{p.students} students{p.pinned ? ' · pinned' : ''}</span>
                    </button>
                  ))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RoomSheets({ data, search }: { data: ExamGrid; search: string }) {
  const q = search.trim().toLowerCase()
  const days = new Map(data.days.map((d) => [d.date, d.label]))
  return (
    <div className="space-y-3">
      {data.rooms.map((slot) => {
        const rooms = slot.rooms.filter((r) => !q || r.room.toLowerCase().includes(q) || r.papers.some((p) => p.codes.toLowerCase().includes(q)))
        if (rooms.length === 0) return null
        const session = data.sessions[slot.session]
        return (
          <section key={`${slot.day}-${slot.session}`} className="rounded-lg border border-line bg-card p-3 text-sm">
            <h2 className="font-semibold">{days.get(slot.day) ?? slot.day} · {session.start}–{session.end}</h2>
            <table className="mt-2 w-full text-left text-xs">
              <thead className="text-muted"><tr><th className="py-1">Room</th><th>Paper</th><th>Class row</th><th>Students</th><th>Invigilator</th></tr></thead>
              <tbody>
                {rooms.flatMap((room) => room.papers.flatMap((p) => p.rows.map((row, i) => (
                  <tr key={`${room.room}-${p.codes}-${i}`} className="border-t border-line">
                    <td className="py-1">{room.room}</td><td>{p.codes}</td>
                    <td>{row.row}{row.odel ? ' (ODEL)' : ''}</td><td>{row.students}</td>
                    <td>{p.invigilator ?? '—'}{p.main ? ' (main)' : ` (extra; main: ${p.main_invigilator ?? '—'})`}</td>
                  </tr>
                ))))}
              </tbody>
            </table>
          </section>
        )
      })}
    </div>
  )
}

function MoveDialog({ termId, draftId, data, paper, onClose }: {
  termId: string; draftId: string; data: ExamGrid; paper: ExamGridPaper; onClose: () => void
}) {
  const move = useMoveExamPaper(termId, draftId)
  const [day, setDay] = useState(paper.day ?? data.days[0]?.date ?? '')
  const [session, setSession] = useState(paper.session ?? 0)
  return (
    <div role="dialog" aria-modal="true" aria-label={`Move ${paper.codes}`} className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-md space-y-3 rounded-xl bg-card p-5 text-sm shadow-xl">
        <h2 className="text-lg font-semibold">Move {paper.codes}</h2>
        <p className="text-muted">{paper.title} · {paper.students} students. The move is checked, and both sessions are re-seated. It stays pinned.</p>
        <label className="block">Date
          <select value={day} onChange={(e) => setDay(e.target.value)} className="mt-1 block w-full rounded-md border border-line px-2 py-1">
            {data.days.map((d) => <option key={d.date} value={d.date}>{d.label}</option>)}
          </select>
        </label>
        <label className="block">Session
          <select value={session} onChange={(e) => setSession(Number(e.target.value))} className="mt-1 block w-full rounded-md border border-line px-2 py-1">
            {data.sessions.map((s, i) => <option key={s.start} value={i}>{s.start}–{s.end}</option>)}
          </select>
        </label>
        {move.isError && <p role="alert" className="text-danger">{errorMessage(move.error)}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-md border border-line px-3 py-2">Cancel</button>
          <button onClick={() => move.mutate({ paperId: paper.id, day, session }, { onSuccess: onClose })} disabled={move.isPending}
            className="rounded-md bg-brand px-4 py-2 text-white disabled:opacity-50">Move</button>
        </div>
      </div>
    </div>
  )
}
