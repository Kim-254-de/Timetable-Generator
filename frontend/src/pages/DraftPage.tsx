import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import clsx from 'clsx'
import { Download, X } from 'lucide-react'
import { TimetableGrid } from '@/components/TimetableGrid'
import { errorBody, errorMessage } from '@/lib/api'
import { DAYS, DAY_NAMES, FIRST_HOUR, HOURS, RULES, SCORE_LABELS, hh, slotDay, slotHour } from '@/lib/format'
import { exportUrl, useCopyDraft, useGrid, useMoveSession, usePublish, useResolve, useRooms, useTerm } from '@/lib/queries'
import type { Cell, View } from '@/lib/types'

const VIEWS: [View, string][] = [['row', 'Class rows'], ['room', 'Rooms'], ['department', 'Departments']]

export function DraftPage() {
  const { termId = '', draftId = '' } = useParams()
  const navigate = useNavigate()
  const [view, setView] = useState<View>('row')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Cell | null>(null)
  const [replaceUploaded, setReplaceUploaded] = useState(false)
  const [keepPublished, setKeepPublished] = useState(false)
  const grid = useGrid(draftId, view)
  const term = useTerm(termId)
  const move = useMoveSession(draftId)
  const resolve = useResolve(termId, draftId)
  const copy = useCopyDraft(termId, draftId)
  const publish = usePublish(termId, draftId)

  const entities = useMemo(() => {
    const q = search.trim().toLowerCase()
    const all = grid.data?.entities ?? []
    if (!q) return all
    return all.filter((e) => e.label.toLowerCase().includes(q) || e.cells.some((c) => c.unit_code.toLowerCase().includes(q)))
  }, [grid.data, search])

  if (grid.isPending) return <p className="text-sm text-muted">Loading the draft…</p>
  if (grid.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(grid.error)}</p>
  const draft = grid.data.draft
  const editable = draft.status === 'draft'
  const highlight = new Set(draft.violations.flatMap((v) => v.session_keys))
  const moveFailure = move.isError ? errorBody(move.error) : undefined
  const needsReplace = term.data?.readiness.snapshot?.published_version == null && (term.data?.publications.length ?? 0) === 0

  const doMove = (key: string, slot: number) =>
    move.mutate({ key, day: slotDay(slot), start_time: hh(slotHour(slot)) })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to={`/terms/${termId}`} className="text-sm text-brand-ink">← Back to the term</Link>
          <h1 className="text-xl font-semibold">{draft.name}</h1>
          <p className="text-sm text-muted">
            {draft.session_count} sessions · {draft.pinned} pinned · <span className="capitalize">{draft.status}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">Download:</span>
          {([['pdf', 'PDF'], ['docx', 'Word'], ['xlsx', 'Excel']] as const).map(([format, label]) => (
            <a key={format} href={exportUrl(draftId, view, format)}
              className="inline-flex items-center gap-1 rounded-md border border-line bg-card px-3 py-2">
              <Download size={16} /> {label}
            </a>
          ))}
          {editable ? (
            <>
              {(term.data?.publications.length ?? 0) > 0 && (
                <label className="flex items-center gap-1" title="For a department imported after publishing: its classes are added around the published ones.">
                  <input type="checkbox" checked={keepPublished} onChange={(e) => setKeepPublished(e.target.checked)} />
                  Keep the published classes
                </label>
              )}
              <button onClick={() => resolve.mutate({ time_limit_s: 600, keep_published: keepPublished }, { onSuccess: () => navigate(`/terms/${termId}?tab=runs`) })}
                disabled={resolve.isPending} className="rounded-md border border-line bg-card px-3 py-2">
                {keepPublished ? 'Re-solve around the published classes' : 'Re-solve around pins'}
              </button>
              {needsReplace && (
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={replaceUploaded} onChange={(e) => setReplaceUploaded(e.target.checked)} />
                  Replace the uploaded timetable
                </label>
              )}
              <button onClick={() => publish.mutate(replaceUploaded)} disabled={!draft.publishable || publish.isPending}
                className="rounded-md bg-brand px-4 py-2 font-medium text-white disabled:opacity-50"
                title={draft.publishable ? 'Approve this timetable and publish it (sent to SMARTTT when connected)' : 'Fix the hard-rule problems first'}>
                {publish.isPending ? 'Publishing…' : 'Approve and publish'}
              </button>
            </>
          ) : (
            <button onClick={() => copy.mutate(undefined, { onSuccess: (d) => navigate(`/terms/${termId}/drafts/${d.id}`) })}
              className="rounded-md border border-line bg-card px-3 py-2">Copy to a new draft</button>
          )}
        </div>
      </div>

      {publish.isSuccess && (
        <p role="status" className="rounded-md bg-success-soft px-3 py-2 text-sm text-success">
          Approved as version {publish.data.version}. Departments now see each class's day, time and room.{' '}
          {publish.data.smarttt.sent === false
            ? `Not yet sent to SMARTTT: ${publish.data.smarttt.reason ?? 'SMARTTT is not connected'}.`
            : 'Students now see it in SMARTTT.'}
        </p>
      )}
      {publish.isError && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{errorMessage(publish.error)}</p>}
      {resolve.isError && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{errorMessage(resolve.error)}</p>}

      <section className="grid gap-3 md:grid-cols-[1fr_auto]">
        <div className="flex flex-wrap gap-2 rounded-lg border border-line bg-card p-3 text-xs">
          {SCORE_LABELS.map(([k, label]) => (
            <span key={k} className="rounded bg-surface px-2 py-1">{label}: <b>{draft.soft_scores[k] ?? 0}</b></span>
          ))}
        </div>
        <div className={clsx('rounded-lg border p-3 text-xs', draft.violation_count ? 'border-danger/40 bg-danger-soft' : 'border-success/40 bg-success-soft')}>
          {draft.violation_count
            ? <>{draft.violation_count} hard-rule problems (outlined in red)</>
            : 'No hard-rule problems'}
          {(draft.stale.missing.length > 0 || draft.stale.extra.length > 0) && (
            <span className="block text-warning">Groups or hours changed since this draft was made; run again.</span>
          )}
        </div>
      </section>
      {draft.violations.length > 0 && (
        <ul className="max-h-32 overflow-y-auto rounded-lg border border-danger/40 bg-card p-3 text-xs text-danger">
          {draft.violations.map((v) => <li key={v.message}><b>{RULES[v.rule] ?? v.rule}:</b> {v.message}</li>)}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {VIEWS.map(([v, label]) => (
          <button key={v} onClick={() => setView(v)}
            className={clsx('rounded-full px-3 py-1 text-sm', view === v ? 'bg-brand text-white' : 'border border-line bg-card')}>
            {label}
          </button>
        ))}
        <input type="search" value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter by class row, room or unit" className="ml-auto w-72 rounded-md border border-line px-3 py-1.5 text-sm" />
      </div>
      {editable && <p className="text-xs text-muted">Drag a class to another hour to move it; moved classes are pinned. Click a class to change its room.</p>}
      {moveFailure && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
          Not moved: {moveFailure.message}
        </p>
      )}

      <TimetableGrid entities={entities} view={view} editable={editable} highlight={highlight} onMove={doMove} onSelect={setSelected} />

      {selected && (
        <CellPanel cell={selected} termId={termId} editable={editable} onClose={() => setSelected(null)}
          onSave={(body) => move.mutate({ key: selected.key, ...body }, { onSuccess: () => setSelected(null) })}
          saving={move.isPending} />
      )}
    </div>
  )
}

interface CellPanelProps {
  cell: Cell
  termId: string
  editable: boolean
  saving: boolean
  onClose: () => void
  onSave: (body: { day?: string; start_time?: string; room_id?: string; pinned?: boolean }) => void
}

function CellPanel({ cell, termId, editable, saving, onClose, onSave }: CellPanelProps) {
  const rooms = useRooms(termId)
  const [day, setDay] = useState(cell.day)
  const [hour, setHour] = useState(Number(cell.start_time.slice(0, 2)))
  const [room, setRoom] = useState(cell.room_id)
  const fitting = (rooms.data ?? []).filter((r) => cell.students == null || r.capacity >= cell.students)

  return (
    <aside aria-label={`${cell.unit_code} ${cell.group}`} className="fixed inset-y-0 right-0 z-30 w-full max-w-sm space-y-4 border-l border-line bg-card p-5 shadow-xl">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold">{cell.unit_code} {cell.group}</h2>
          <p className="text-sm text-muted">{cell.day} {cell.start_time}–{cell.end_time} · {cell.room}{cell.students != null && ` · ${cell.students} students`}</p>
        </div>
        <button onClick={onClose} aria-label="Close" className="rounded p-1 hover:bg-surface"><X size={18} /></button>
      </div>
      {editable ? (
        <>
          <label className="block text-sm">Day
            <select value={day} onChange={(e) => setDay(e.target.value as typeof day)} className="mt-1 w-full rounded-md border border-line px-2 py-1">
              {DAYS.map((d) => <option key={d} value={d}>{DAY_NAMES[d]}</option>)}
            </select>
          </label>
          <label className="block text-sm">Starts at
            <select value={hour} onChange={(e) => setHour(Number(e.target.value))} className="mt-1 w-full rounded-md border border-line px-2 py-1">
              {Array.from({ length: HOURS - cell.length + 1 }, (_, i) => FIRST_HOUR + i).map((h) => <option key={h} value={h}>{hh(h)}</option>)}
            </select>
          </label>
          <label className="block text-sm">Room
            <select value={room} onChange={(e) => setRoom(e.target.value)} className="mt-1 w-full rounded-md border border-line px-2 py-1">
              {fitting.map((r) => <option key={r.id} value={r.id}>{r.code} ({r.capacity}, {r.room_type.replace('_', ' ')})</option>)}
            </select>
          </label>
          <div className="flex justify-between gap-2">
            <button onClick={() => onSave({ pinned: !cell.pinned })} disabled={saving} className="rounded-md border border-line px-3 py-2 text-sm">
              {cell.pinned ? 'Unpin' : 'Pin here'}
            </button>
            <button onClick={() => onSave({ day, start_time: hh(hour), room_id: room })} disabled={saving}
              className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
              {saving ? 'Checking…' : 'Move'}
            </button>
          </div>
        </>
      ) : (
        <p className="text-sm text-muted">This draft is an approved version. It shows exactly as approved, whatever has changed since. Copy it to a new draft to change it.</p>
      )}
    </aside>
  )
}
