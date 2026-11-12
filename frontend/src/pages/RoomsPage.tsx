import { useMemo, useState, type FormEvent } from 'react'
import clsx from 'clsx'
import { BulkPaste, type BulkColumn } from '@/components/BulkPaste'
import { Dialog, Field, inputClass } from '@/components/Dialog'
import { SlotPicker } from '@/components/SlotPicker'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { errorMessage } from '@/lib/api'
import { useBulkRooms, useDeleteRoom, useRoomList, useSaveRoom, useSyncRooms, type RoomInput } from '@/lib/queries'
import type { RoomRecord, RoomType } from '@/lib/types'

export const ROOM_TYPE_NAMES: Record<RoomType, string> = { lecture_hall: 'Lecture hall', lab: 'Lab', seminar: 'Seminar room' }

const COLUMNS: BulkColumn[] = [
  { key: 'code', label: 'Code', example: 'UTC-AB3', required: true },
  { key: 'building', label: 'Building', example: 'UTC' },
  { key: 'capacity', label: 'Capacity', example: '120', required: true },
  { key: 'room_type', label: 'Room type', example: 'Lecture hall', hint: 'Lecture hall, Lab or Seminar room' },
  { key: 'available', label: 'Available', example: 'Yes', hint: 'Yes or No (a closed room is never used)' },
  { key: 'exam_seats', label: 'Exam seats', example: '', hint: "Leave blank: capacity x the term's spacing (0.9). Only for a room that can't be used at that share (fixed benches)." },
  { key: 'for_exams', label: 'For exams', example: 'Yes', hint: 'No keeps the room out of exams.' },
]

/** Exam seats when the room has no fixed number: capacity x the default spacing (the term can change it). */
const DEFAULT_SPACING = 0.9

/** The Directorate's list of lecture halls, labs and seminar rooms, shared by every term. */
export function RoomsPage() {
  const rooms = useRoomList()
  const bulk = useBulkRooms()
  const sync = useSyncRooms()
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<RoomRecord | 'new' | null>(null)
  const [hours, setHours] = useState<RoomRecord | null>(null)
  const [pasting, setPasting] = useState(false)
  const save = useSaveRoom()

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (rooms.data ?? [])
      .filter((r) => !q || r.code.toLowerCase().includes(q) || r.building.toLowerCase().includes(q))
      .sort((a, b) => Number(b.active) - Number(a.active) || a.code.localeCompare(b.code))
  }, [rooms.data, query])
  const open = (rooms.data ?? []).filter((r) => r.active)
  const closed = (rooms.data?.length ?? 0) - open.length
  const seats = open.reduce((n, r) => n + r.capacity, 0)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold text-ink">Lecture halls</h1>
          <p className="text-sm text-muted">
            {open.length} open{closed > 0 && ` · ${closed} closed`} · {seats.toLocaleString()} seats · shared by every term
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <details className="relative">
            <summary className="inline-flex h-11 cursor-pointer list-none items-center gap-1.5 rounded-xl border border-line bg-card px-4 text-sm font-semibold text-ink hover:bg-surface [&::-webkit-details-marker]:hidden">
              {sync.isPending ? 'Bringing in…' : 'Import'} <span aria-hidden>▾</span>
            </summary>
            <div className="absolute right-0 z-10 mt-1 w-64 overflow-hidden rounded-xl border border-line bg-card py-1 text-sm shadow-lg">
              <button type="button" onClick={(e) => { (e.currentTarget.closest('details') as HTMLDetailsElement).open = false; sync.mutate() }}
                disabled={sync.isPending} className="block w-full cursor-pointer px-4 py-2 text-left hover:bg-surface">
                <span className="block font-medium text-ink">Bring in from SMARTTT</span>
                <span className="block text-xs text-muted">Rooms and capacities the admin set there</span>
              </button>
              <button type="button" onClick={(e) => { (e.currentTarget.closest('details') as HTMLDetailsElement).open = false; setPasting(true) }}
                className="block w-full cursor-pointer px-4 py-2 text-left hover:bg-surface">
                <span className="block font-medium text-ink">Paste from Excel</span>
                <span className="block text-xs text-muted">A sheet or CSV, one room per line</span>
              </button>
            </div>
          </details>
          <Button onClick={() => setEditing('new')}>+ Add a lecture hall</Button>
        </div>
      </div>

      <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search code or building" aria-label="Search code or building"
        className="h-11 w-full max-w-sm rounded-xl border border-line bg-card px-4 text-sm" />
      {rooms.isError && <p role="alert" className="rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">{errorMessage(rooms.error)}</p>}
      {sync.isError && <p role="alert" className="rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">{errorMessage(sync.error)}</p>}
      {sync.data && (
        <p role="status" className="rounded-xl bg-success-soft px-4 py-3 text-sm text-success">
          From SMARTTT: {sync.data.added.length} added, {sync.data.updated.length} updated.
          {sync.data.merged.length > 0 && ` One room under two codes, merged: ${sync.data.merged.join(', ')}.`}
          {sync.data.only_here.length > 0 && ` Only here, not in SMARTTT, so not used for exams unless you choose them: ${sync.data.only_here.join(', ')}.`}
        </p>
      )}

      <Card className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs font-semibold uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-3">Code</th><th className="px-4 py-3">Building</th><th className="px-4 py-3">Capacity</th>
              <th className="px-4 py-3">Type</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Blocked hours</th>
              <th className="px-4 py-3">Exam seats</th><th />
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className={clsx('border-t border-line', !r.active && 'text-muted')}>
                <td className="px-4 py-3 font-semibold">{r.code}</td>
                <td className="px-4 py-3">{r.building}</td>
                <td className="px-4 py-3">{r.capacity}</td>
                <td className="px-4 py-3">{ROOM_TYPE_NAMES[r.room_type]}</td>
                <td className="px-4 py-3">
                  <span className={clsx('rounded-full px-2.5 py-0.5 text-xs font-semibold', r.active ? 'bg-success-soft text-success' : 'bg-surface text-muted ring-1 ring-line')}>
                    {r.active ? 'Open' : 'Closed'}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <button onClick={() => setHours(r)} className="cursor-pointer font-medium text-brand-ink hover:underline">
                    {r.unavailable.length ? `${r.unavailable.length} hours` : 'None'}
                  </button>
                </td>
                <td className="px-4 py-3">
                  {!r.for_exams
                    ? <span className="text-muted">Not for exams</span>
                    : r.exam_seats ?? <span title={`Capacity x the term's spacing (${DEFAULT_SPACING} unless changed)`}>{Math.floor(r.capacity * DEFAULT_SPACING)} <span className="text-xs text-muted">auto</span></span>}
                </td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => setEditing(r)} className="cursor-pointer font-semibold text-brand-ink hover:underline">Edit</button>
                </td>
              </tr>
            ))}
            {rooms.data?.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-muted">No lecture halls yet. Add them one by one, or import them.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {editing && <RoomForm room={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {hours && (
        <SlotPicker title={`Hours ${hours.code} can't be used`} help="Click the hours when this room is closed (e.g. maintenance)."
          initial={hours.unavailable} busy={save.isPending} error={save.isError ? errorMessage(save.error) : null}
          onClose={() => setHours(null)}
          onSave={(slots) => save.mutate({ id: hours.id, body: { unavailable: slots } }, { onSuccess: () => setHours(null) })} />
      )}
      {pasting && (
        <BulkPaste title="Paste lecture halls" columns={COLUMNS} templateName="lecture-halls.csv"
          submit={(rows) => bulk.mutateAsync(rows)} onClose={() => setPasting(false)} />
      )}
    </div>
  )
}

function RoomForm({ room, onClose }: { room: RoomRecord | null; onClose: () => void }) {
  const save = useSaveRoom()
  const remove = useDeleteRoom()
  const [confirming, setConfirming] = useState(false)
  const [form, setForm] = useState<RoomInput>({
    code: room?.code ?? '',
    building: room?.building ?? '',
    capacity: room?.capacity ?? 100,
    room_type: room?.room_type ?? 'lecture_hall',
    active: room?.active ?? true,
    exam_seats: room?.exam_seats ?? null,
    for_exams: room ? room.exam_override : null,
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({ id: room?.id, body: { ...form, exam_seats: form.exam_seats || (room ? 0 : null) } }, { onSuccess: onClose })
  }
  return (
    <Dialog title={room ? `Edit ${room.code}` : 'Add a lecture hall'} onClose={onClose}>
      <form onSubmit={submit} className="mt-3 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Code"><input required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="TC 7" className={inputClass} /></Field>
          <Field label="Building"><input value={form.building} onChange={(e) => setForm({ ...form, building: e.target.value })} placeholder="Tuition Complex" className={inputClass} /></Field>
          <Field label="Capacity (seats)">
            <input required type="number" min={1} max={5000} value={form.capacity} onChange={(e) => setForm({ ...form, capacity: Number(e.target.value) })} className={inputClass} />
          </Field>
          <Field label="Room type">
            <select value={form.room_type} onChange={(e) => setForm({ ...form, room_type: e.target.value as RoomType })} className={inputClass}>
              {Object.entries(ROOM_TYPE_NAMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} />
          Available for teaching
        </label>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Fixed exam seats" hint="Leave blank: exam seats are capacity x the term's spacing (0.9). Only for a room that can't be used at that share (e.g. fixed benches).">
            <input type="number" min={1} max={form.capacity} value={form.exam_seats ?? ''}
              onChange={(e) => setForm({ ...form, exam_seats: e.target.value === '' ? null : Number(e.target.value) })} className={inputClass} />
          </Field>
          <Field label="Used for exams" hint={`The administrator says ${room?.admin_for_exams === false ? 'no' : 'yes'}. Your choice overrules theirs.`}>
            <select value={form.for_exams === null || form.for_exams === undefined ? '' : String(form.for_exams)} className={inputClass}
              onChange={(e) => setForm({ ...form, for_exams: e.target.value === '' ? null : e.target.value === 'true' })}>
              <option value="">{`As the administrator set (${room?.admin_for_exams === false ? 'no' : 'yes'})`}</option>
              <option value="true">Yes, use it</option>
              <option value="false">No, keep it out</option>
            </select>
          </Field>
        </div>
        {save.isError && <p role="alert" className="text-sm text-danger">{errorMessage(save.error)}</p>}
        {remove.isError && <p role="alert" className="text-sm text-danger">{errorMessage(remove.error)}</p>}
        {room && confirming ? (
          <div role="alertdialog" aria-label={`Delete ${room.code}?`} className="space-y-3 rounded-xl bg-danger-soft p-4 text-sm text-danger">
            <p className="font-semibold">Delete {room.code}? This can't be undone.</p>
            {room.in_use > 0 && <p>It is used by {room.in_use} classes in saved timetables.</p>}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setConfirming(false)}>Keep it</Button>
              <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate(room.id, { onSuccess: onClose })}>Delete</Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            {room && <Button variant="ghost" className="mr-auto px-3 text-danger" onClick={() => setConfirming(true)}>Delete this room</Button>}
            <Button variant="secondary" className="ml-auto" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>Save</Button>
          </div>
        )}
      </form>
    </Dialog>
  )
}
