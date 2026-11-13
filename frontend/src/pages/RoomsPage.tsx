import { useMemo, useState, type FormEvent } from 'react'
import clsx from 'clsx'
import { Building2, Plus, Search } from 'lucide-react'
import { BulkPaste, type BulkColumn } from '@/components/BulkPaste'
import { Dialog, Field, inputClass } from '@/components/Dialog'
import { SlotPicker } from '@/components/SlotPicker'
import { Card, IconBox, PageTitle, Pill, btn } from '@/components/ui'
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

/** The Directorate's list of lecture halls, labs and seminar rooms, shared by every term. */
export function RoomsPage() {
  const rooms = useRoomList()
  const remove = useDeleteRoom()
  const bulk = useBulkRooms()
  const sync = useSyncRooms()
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<RoomRecord | 'new' | null>(null)
  const [hours, setHours] = useState<RoomRecord | null>(null)
  const [pasting, setPasting] = useState(false)
  const save = useSaveRoom()

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (rooms.data ?? []).filter((r) => !q || r.code.toLowerCase().includes(q) || r.building.toLowerCase().includes(q))
  }, [rooms.data, query])
  const seats = (rooms.data ?? []).filter((r) => r.active).reduce((n, r) => n + r.capacity, 0)

  // One table per building, buildings in name order; rooms with no building last, under "Other".
  const buildings = useMemo(() => {
    const groups = new Map<string, RoomRecord[]>()
    for (const r of shown) {
      const key = r.building.trim() || 'Other'
      groups.set(key, [...(groups.get(key) ?? []), r])
    }
    return [...groups.entries()]
      .sort(([a], [b]) => (a === 'Other' ? 1 : b === 'Other' ? -1 : a.localeCompare(b)))
      .map(([name, list]) => ({ name, rooms: list.sort((x, y) => x.code.localeCompare(y.code, undefined, { numeric: true })) }))
  }, [shown])

  return (
    <div className="space-y-4">
      <PageTitle title="Lecture halls" crumb="Shared by every term" />
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex min-w-0 flex-1 basis-64 items-center gap-2 rounded-xl border border-line bg-card px-3 text-muted">
          <Search className="size-4" aria-hidden />
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search code or building"
            aria-label="Search lecture halls" className="min-w-0 flex-1 border-0 bg-transparent py-2.5 text-ink outline-none focus-visible:outline-none" />
        </label>
        <button type="button" onClick={() => sync.mutate()} disabled={sync.isPending} className={btn.secondary}
          title="The rooms the admin set in SMARTTT: capacities and exam use. Exam seats, blocked hours and your own exam choice stay.">
          {sync.isPending ? 'Bringing in…' : 'Bring in from SMARTTT'}
        </button>
        <button type="button" onClick={() => setPasting(true)} className={btn.secondary}>Paste from Excel</button>
        <button type="button" onClick={() => setEditing('new')} className={btn.primary}><Plus className="size-4" aria-hidden /> Add hall</button>
      </div>
      <p className="text-sm text-muted">{rooms.data?.length ?? 0} rooms in {buildings.length} buildings · {seats.toLocaleString()} seats available. Used by every term.</p>
      {rooms.isError && <p role="alert" className="text-sm text-danger">{errorMessage(rooms.error)}</p>}
      {remove.isError && <p role="alert" className="text-sm text-danger">{errorMessage(remove.error)}</p>}
      {sync.isError && <p role="alert" className="text-sm text-danger">{errorMessage(sync.error)}</p>}
      {sync.data && (
        <p role="status" className="rounded-lg bg-success-soft px-4 py-3 text-sm text-success">
          From SMARTTT: {sync.data.added.length} added, {sync.data.updated.length} updated.
          {sync.data.merged.length > 0 && ` One room under two codes, merged: ${sync.data.merged.join(', ')}.`}
          {sync.data.only_here.length > 0 && ` Only here, not in SMARTTT, so not used for exams unless you choose them: ${sync.data.only_here.join(', ')}.`}
        </p>
      )}
      {rooms.data?.length === 0 && (
        <Card><p className="text-center text-sm text-muted">No lecture halls yet. Add them one by one, or paste the list from Excel.</p></Card>
      )}
      {rooms.data && rooms.data.length > 0 && shown.length === 0 && <p className="text-sm text-muted">No hall matches.</p>}
      {buildings.map((b) => (
        <section key={b.name} aria-label={b.name} className="overflow-hidden rounded-xl border border-line bg-card">
          <div className="flex flex-wrap items-center gap-3 border-b border-line bg-surface px-5 py-3">
            <IconBox icon={Building2} />
            <h2 className="min-w-0 flex-1 text-[17px] font-semibold">{b.name}</h2>
            <span className="text-sm text-muted">
              {b.rooms.length} {b.rooms.length === 1 ? 'hall' : 'halls'} · {b.rooms.filter((r) => r.active).reduce((n, r) => n + r.capacity, 0).toLocaleString()} seats
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="px-5 py-2.5 font-medium">Hall</th><th className="px-3 py-2.5 font-medium">Type</th>
                  <th className="px-3 py-2.5 text-right font-medium">Seats</th>
                  <th className="px-3 py-2.5 text-right font-medium" title="Blank: capacity x the term's spacing">Exam seats</th>
                  <th className="px-3 py-2.5 font-medium">Blocked hours</th>
                  <th className="px-5 py-2.5"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {b.rooms.map((r) => (
                  <tr key={r.id} className={clsx('border-t border-line', !r.active && 'text-muted')}>
                    <td className="px-5 py-2.5 font-semibold">{r.code}{!r.active && <span className="ml-2"><Pill tone="muted">Closed</Pill></span>}</td>
                    <td className="px-3 py-2.5"><Pill>{ROOM_TYPE_NAMES[r.room_type]}</Pill></td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{r.capacity}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {r.for_exams ? (r.exam_seats ?? <span className="text-muted">× spacing</span>) : <span className="text-muted">Not for exams</span>}
                    </td>
                    <td className="px-3 py-2.5">
                      <button type="button" onClick={() => setHours(r)} className={btn.quiet}>{r.unavailable.length ? `${r.unavailable.length} hours` : 'None'}</button>
                    </td>
                    <td className="whitespace-nowrap px-5 py-2 text-right">
                      <button type="button" onClick={() => setEditing(r)} className={btn.quiet}>Edit</button>
                      <button type="button" onClick={() => { if (window.confirm(`Delete ${r.code}?`)) remove.mutate(r.id) }}
                        className={clsx(btn.quiet, 'text-danger hover:bg-danger-soft')}
                        title={r.in_use ? `Used by ${r.in_use} classes in saved timetables` : undefined}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
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
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className={btn.secondary}>Cancel</button>
          <button type="submit" disabled={save.isPending} className={btn.primary}>Save</button>
        </div>
      </form>
    </Dialog>
  )
}
