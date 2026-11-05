import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import clsx from 'clsx'
import { Download } from 'lucide-react'
import { errorMessage } from '@/lib/api'
import { dateTime } from '@/lib/format'
import { examExportUrl, useChangeExamVenue, useExamDraft, useExamDraftAction, useMoveExamPaper, useSetDirectorInvigilators } from '@/lib/queries'
import type { ExamDraftSummary, ExamGrid, ExamGridPaper } from '@/lib/types'

const roomsOf = (p: ExamGridPaper) => [...new Set(p.seating.map((s) => s.room))].sort()

/**
 * An exam draft as the Director reviews it: the date x session grid of
 * `paper -> rooms` (like the printed timetable), or the room sheets. A paper
 * can be moved or given another venue (checked); the draft is shared with departments for
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
            {draft.soft_scores.postgraduate_extra_rooms ? ` · Postgraduate papers in ${draft.soft_scores.postgraduate_extra_rooms} extra rooms` : ''}
            {draft.soft_scores.postgraduate_outside_building ? ` · ${draft.soft_scores.postgraduate_outside_building} postgraduate papers outside the postgraduate room's building` : ''}
            {draft.soft_scores.common_midday ? ` · ${draft.soft_scores.common_midday} common papers in a middle session` : ''}
            {draft.soft_scores.over_session_limit ? ` · ${draft.soft_scores.over_session_limit} sessions fuller than the limit, so more papers are split across rooms` : ''}
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

/** Students of the paper in a room, and what else that session has in each room. */
function freeSeats(data: ExamGrid, paper: ExamGridPaper): Map<string, number> {
  const used = new Map<string, number>()
  for (const p of data.papers) {
    if (p.day !== paper.day || p.session !== paper.session) continue
    for (const s of p.seating) used.set(s.room, (used.get(s.room) ?? 0) + s.students)
  }
  return new Map(data.exam_rooms.map((r) => [r.code, r.seats - (used.get(r.code) ?? 0)]))
}

/** The other papers of the session in a room, with their students there. */
function papersIn(data: ExamGrid, paper: ExamGridPaper, room: string): { codes: string; students: number }[] {
  return data.papers
    .filter((p) => p.id !== paper.id && p.day === paper.day && p.session === paper.session)
    .map((p) => ({ codes: p.codes, students: p.seating.filter((s) => s.room === room).reduce((n, s) => n + s.students, 0) }))
    .filter((p) => p.students > 0)
}

/** One of the paper's rooms and where its students could go instead; a full room can be cleared for them. */
function VenueRow({ termId, draftId, data, paper, room }: { termId: string; draftId: string; data: ExamGrid; paper: ExamGridPaper; room: string }) {
  const change = useChangeExamVenue(termId, draftId)
  const [to, setTo] = useState('')
  const [made, setMade] = useState<NonNullable<ExamDraftSummary['made_room']>>([])
  const free = freeSeats(data, paper)
  const students = paper.seating.filter((s) => s.room === room).reduce((n, s) => n + s.students, 0)
  const options = data.exam_rooms
    .filter((r) => r.code !== room)
    .sort((a, b) => a.code.localeCompare(b.code))
  const chosen = data.exam_rooms.find((r) => r.code === to)
  const mine = paper.seating.filter((s) => s.room === to).reduce((n, s) => n + s.students, 0)
  const tooSmall = !!chosen && students + mine > chosen.seats
  const full = !!chosen && !tooSmall && (free.get(to) ?? 0) < students
  const submit = () =>
    change.mutate({ paperId: paper.id, from_room: room, to_room: to, make_room: full }, {
      onSuccess: (summary) => { setMade(summary.made_room ?? []); setTo('') },
    })
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="w-28 font-medium">{room} <span className="font-normal text-muted">({students})</span></span>
        <span aria-hidden>→</span>
        <select aria-label={`New venue instead of ${room}`} value={to} onChange={(e) => { setTo(e.target.value); setMade([]) }} className="min-w-0 flex-1 rounded-md border border-line px-2 py-1">
          <option value="">Choose a venue</option>
          {options.map((r) => {
            const left = free.get(r.code) ?? r.seats
            const own = paper.seating.filter((s) => s.room === r.code).reduce((n, s) => n + s.students, 0)
            const label = students + own > r.seats ? 'too small' : left < students ? 'full: make room' : `${left} of ${r.seats} seats free`
            return <option key={r.code} value={r.code} disabled={students + own > r.seats}>{r.code} · {label}</option>
          })}
        </select>
        <button type="button" disabled={!to || tooSmall || change.isPending} onClick={submit}
          className="rounded-md border border-line px-3 py-1 disabled:opacity-50">{full ? 'Make room' : 'Change'}</button>
      </div>
      {full && (
        <p className="mt-1 text-xs text-muted">
          {to} has {Math.max(free.get(to) ?? 0, 0)} free seats this session. Making room moves {papersIn(data, paper, to).map((p) => `${p.codes} (${p.students})`).join(', ') || 'other papers'} out
          to free seats elsewhere in the session, as few papers as will do. Papers whose venue you chose stay. Check their invigilators afterwards.
        </p>
      )}
      {made.length > 0 && (
        <p role="status" className="mt-1 text-xs">
          Made room: {made.map((m) => `${m.paper} moved from ${m.from} to ${m.to.join(', ')}`).join('; ')}.
        </p>
      )}
      {change.isError && <p role="alert" className="mt-1 text-danger">{errorMessage(change.error)}</p>}
    </div>
  )
}

/** A paper the Director uploaded has no department to name its invigilators. */
function DirectorInvigilators({ termId, paper }: { termId: string; paper: ExamGridPaper }) {
  const save = useSetDirectorInvigilators(termId)
  const slots = [{ key: '', label: paper.main_room ? `Main (${paper.main_room})` : 'Main' }, ...paper.extra_rooms.map((r) => ({ key: r, label: r }))]
  const [named, setNamed] = useState<Record<string, { staff_number: string; name: string }>>(
    Object.fromEntries(slots.map((s) => [s.key, { staff_number: paper.invigilators[s.key]?.staff_number ?? '', name: paper.invigilators[s.key]?.name ?? '' }])),
  )
  const set = (key: string, patch: Partial<{ staff_number: string; name: string }>) => setNamed({ ...named, [key]: { ...named[key], ...patch } })
  return (
    <fieldset className="space-y-2 border-t border-line pt-3">
      <legend className="font-semibold">Invigilators</legend>
      <p className="text-xs text-muted">You uploaded this paper, so you name them. SMARTTT needs to know the staff numbers when you publish.</p>
      {slots.map((s) => (
        <div key={s.key} className="flex flex-wrap items-center gap-2">
          <span className="w-28">{s.label}</span>
          <input aria-label={`Staff number, ${s.label}`} placeholder="Staff number" value={named[s.key]?.staff_number ?? ''} onChange={(e) => set(s.key, { staff_number: e.target.value })} className="w-32 rounded-md border border-line px-2 py-1" />
          <input aria-label={`Name, ${s.label}`} placeholder="Name" value={named[s.key]?.name ?? ''} onChange={(e) => set(s.key, { name: e.target.value })} className="min-w-0 flex-1 rounded-md border border-line px-2 py-1" />
        </div>
      ))}
      {save.isError && <p role="alert" className="text-danger">{errorMessage(save.error)}</p>}
      {save.isSuccess && <p role="status" className="text-muted">Saved.</p>}
      <button type="button" disabled={save.isPending} onClick={() => save.mutate({ paperId: paper.id, invigilators: named })} className="rounded-md border border-line px-3 py-1">Save invigilators</button>
    </fieldset>
  )
}

function MoveDialog({ termId, draftId, data, paper: picked, onClose }: {
  termId: string; draftId: string; data: ExamGrid; paper: ExamGridPaper; onClose: () => void
}) {
  const move = useMoveExamPaper(termId, draftId)
  const paper = data.papers.find((p) => p.id === picked.id) ?? picked // refreshed after a change
  const [day, setDay] = useState(paper.day ?? data.days[0]?.date ?? '')
  const [session, setSession] = useState(paper.session ?? 0)
  const rooms = roomsOf(paper)
  return (
    <div role="dialog" aria-modal="true" aria-label={`Change ${paper.codes}`} className="fixed inset-0 z-30 flex items-center justify-center overflow-y-auto bg-black/40 px-4 py-6">
      <div className="max-h-full w-full max-w-lg space-y-3 overflow-y-auto rounded-xl bg-card p-5 text-sm shadow-xl">
        <h2 className="text-lg font-semibold">{paper.codes}</h2>
        <p className="text-muted">{paper.title} · {paper.students} students · {paper.category}.</p>

        <section className="space-y-2">
          <h3 className="font-semibold">Venue</h3>
          {rooms.length === 0
            ? <p className="text-muted">No students known yet, so no room. Enter its numbers and generate again.</p>
            : rooms.map((room) => <VenueRow key={room} termId={termId} draftId={draftId} data={data} paper={paper} room={room} />)}
          {rooms.length > 0 && <p className="text-xs text-muted">Checked for seats. A full room can be cleared: its other papers move to free seats elsewhere in the session. The paper is pinned and keeps this venue when its session is re-seated.</p>}
        </section>

        <section className="space-y-2 border-t border-line pt-3">
          <h3 className="font-semibold">Date and session</h3>
          <p className="text-muted">The move is checked, and both sessions are re-seated, so this paper's venues may change. It stays pinned.</p>
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
          <button onClick={() => move.mutate({ paperId: paper.id, day, session }, { onSuccess: onClose })} disabled={move.isPending}
            className="rounded-md bg-brand px-4 py-2 text-white disabled:opacity-50">Move</button>
        </section>

        {paper.director_paper && paper.seating.length > 0 && <DirectorInvigilators key={paper.extra_rooms.join()} termId={termId} paper={paper} />}

        <div className="flex justify-end">
          <button onClick={onClose} className="rounded-md border border-line px-3 py-2">Close</button>
        </div>
      </div>
    </div>
  )
}
