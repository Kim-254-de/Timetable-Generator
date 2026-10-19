import { useState } from 'react'
import clsx from 'clsx'
import { DAYS, FIRST_HOUR, HOURS } from '@/lib/format'
import { Dialog } from './Dialog'

/** Click hours on the Monday-Friday x 07:00-19:00 grid to block them. */
export function SlotPicker({
  title,
  help,
  initial,
  busy,
  error,
  onClose,
  onSave,
}: {
  title: string
  help: string
  initial: number[]
  busy?: boolean
  error?: string | null
  onClose: () => void
  onSave: (slots: number[]) => void
}) {
  const [slots, setSlots] = useState(new Set(initial))
  const toggle = (s: number) =>
    setSlots((prev) => {
      const next = new Set(prev)
      if (next.has(s)) next.delete(s)
      else next.add(s)
      return next
    })
  return (
    <Dialog title={title} onClose={onClose} wide>
      <p className="text-sm text-slate-600">{help}</p>
      <table className="mt-3 text-xs">
        <thead><tr><th />{Array.from({ length: HOURS }, (_, h) => <th key={h} className="px-1">{FIRST_HOUR + h}</th>)}</tr></thead>
        <tbody>
          {DAYS.map((d, di) => (
            <tr key={d}>
              <th className="pr-2 text-left">{d}</th>
              {Array.from({ length: HOURS }, (_, h) => {
                const s = di * HOURS + h
                return (
                  <td key={h}>
                    <button type="button" aria-pressed={slots.has(s)} aria-label={`${d} ${FIRST_HOUR + h}:00`} onClick={() => toggle(s)}
                      className={clsx('h-6 w-8 rounded border', slots.has(s) ? 'border-red-400 bg-red-200' : 'border-slate-200 bg-slate-50')} />
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" onClick={onClose} className="rounded-md border border-slate-300 px-3 py-2 text-sm">Cancel</button>
        <button type="button" disabled={busy} onClick={() => onSave([...slots].sort((a, b) => a - b))}
          className="rounded-md bg-emerald-700 px-4 py-2 text-sm text-white disabled:opacity-50">Save</button>
      </div>
    </Dialog>
  )
}
