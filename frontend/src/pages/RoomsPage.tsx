import { useMemo, useState, type FormEvent } from 'react'
import clsx from 'clsx'
import { BulkPaste, type BulkColumn } from '@/components/BulkPaste'
import { Dialog, Field, inputClass } from '@/components/Dialog'
import { SlotPicker } from '@/components/SlotPicker'
import { errorMessage } from '@/lib/api'
import { useBulkRooms, useDeleteRoom, useRoomList, useSaveRoom, type RoomInput } from '@/lib/queries'
import type { RoomRecord, RoomType } from '@/lib/types'

export const ROOM_TYPE_NAMES: Record<RoomType, string> = { lecture_hall: 'Lecture hall', lab: 'Lab', seminar: 'Seminar room' }

const COLUMNS: BulkColumn[] = [
  { key: 'code', label: 'Code', example: 'UTC-AB3', required: true },
  { key: 'building', label: 'Building', example: 'UTC' },
  { key: 'capacity', label: 'Capacity', example: '120', required: true },
  { key: 'room_type', label: 'Room type', example: 'Lecture hall', hint: 'Lecture hall, Lab or Seminar room' },
  { key: 'available', label: 'Available', example: 'Yes', hint: 'Yes or No (a closed room is never used)' },
]

/** The Directorate's list of lecture halls, labs and seminar rooms, shared by every term. */
export function RoomsPage() {
  const rooms = useRoomList()
  const remove = useDeleteRoom()
  const bulk = useBulkRooms()
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Lecture halls</h1>
          <p className="text-sm text-muted">
            {rooms.data?.length ?? 0} rooms · {seats.toLocaleString()} seats available. Used by every term.
          </p>
        </div>
        <div className="flex gap-2 text-sm">
          <button onClick={() => setPasting(true)} className="rounded-md border border-line bg-card px-3 py-2">Paste from Excel</button>
          <button onClick={() => setEditing('new')} className="rounded-md bg-brand px-3 py-2 text-white">+ Add a lecture hall</button>
        </div>
      </div>
      <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search code or building"
        className="w-72 rounded-md border border-line px-3 py-1.5 text-sm" />
      {rooms.isError && <p role="alert" className="text-sm text-danger">{errorMessage(rooms.error)}</p>}
      {remove.isError && <p role="alert" className="text-sm text-danger">{errorMessage(remove.error)}</p>}
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Code</th><th className="px-3 py-2">Building</th><th className="px-3 py-2">Capacity</th>
              <th className="px-3 py-2">Type</th><th className="px-3 py-2">Available</th><th className="px-3 py-2">Blocked hours</th><th />
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className={clsx('border-t border-line', !r.active && 'text-muted')}>
                <td className="px-3 py-2 font-medium">{r.code}</td>
                <td className="px-3 py-2">{r.building}</td>
                <td className="px-3 py-2">{r.capacity}</td>
                <td className="px-3 py-2">{ROOM_TYPE_NAMES[r.room_type]}</td>
                <td className="px-3 py-2">{r.active ? 'Yes' : 'Closed'}</td>
                <td className="px-3 py-2">
                  <button onClick={() => setHours(r)} className="text-brand-ink">{r.unavailable.length ? `${r.unavailable.length} hours` : 'None'}</button>
                </td>
                <td className="space-x-3 px-3 py-2 text-right">
                  <button onClick={() => setEditing(r)} className="text-brand-ink">Edit</button>
                  <button onClick={() => { if (window.confirm(`Delete ${r.code}?`)) remove.mutate(r.id) }} className="text-danger"
                    title={r.in_use ? `Used by ${r.in_use} classes in saved timetables` : undefined}>Delete</button>
                </td>
              </tr>
            ))}
            {rooms.data?.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-muted">No lecture halls yet. Add them one by one, or paste the list from Excel.</td></tr>
            )}
          </tbody>
        </table>
      </div>
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
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({ id: room?.id, body: form }, { onSuccess: onClose })
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
        {save.isError && <p role="alert" className="text-sm text-danger">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-2 text-sm">Cancel</button>
          <button type="submit" disabled={save.isPending} className="rounded-md bg-brand px-4 py-2 text-sm text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </Dialog>
  )
}
