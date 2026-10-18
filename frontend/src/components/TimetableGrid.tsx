import { useState, type DragEvent } from 'react'
import clsx from 'clsx'
import { Pin } from 'lucide-react'
import { DAYS, DAY_NAMES, FIRST_HOUR, HOURS, slotDay, slotHour } from '@/lib/format'
import type { Cell, Entity, View } from '@/lib/types'

interface Props {
  entities: Entity[]
  view: View
  editable: boolean
  highlight?: Set<string>
  onMove: (key: string, slot: number) => void
  onSelect: (cell: Cell) => void
}

const LABEL_WIDTH = '11rem'

/** Cells that overlap in time go on separate lines of the same entity, as in the printed timetable. */
function lines(cells: Cell[]): Cell[][] {
  const out: Cell[][] = []
  for (const cell of cells) {
    const line = out.find((l) => l.every((c) => cell.start_slot >= c.start_slot + c.length || c.start_slot >= cell.start_slot + cell.length))
    if (line) line.push(cell)
    else out.push([cell])
  }
  return out.length ? out : [[]]
}

export function TimetableGrid({ entities, view, editable, highlight, onMove, onSelect }: Props) {
  const [over, setOver] = useState<string | null>(null)
  const columns = `${LABEL_WIDTH} repeat(${DAYS.length * HOURS}, minmax(2.1rem, 1fr))`

  const drop = (e: DragEvent, slot: number) => {
    e.preventDefault()
    setOver(null)
    const key = e.dataTransfer.getData('text/session-key')
    if (key) onMove(key, slot)
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-300 bg-white text-[11px]" role="grid" aria-label="Timetable">
      <div className="grid min-w-[110rem]" style={{ gridTemplateColumns: columns }}>
        <div className="sticky left-0 z-10 border-b border-r border-slate-300 bg-slate-100" />
        {DAYS.map((d) => (
          <div key={d} className="border-b border-r border-slate-300 bg-slate-100 py-1 text-center font-semibold"
            style={{ gridColumn: `span ${HOURS}` }}>
            {DAY_NAMES[d]}
          </div>
        ))}
        <div className="sticky left-0 z-10 border-b border-r border-slate-300 bg-slate-100" />
        {DAYS.flatMap((d) =>
          Array.from({ length: HOURS }, (_, h) => (
            <div key={`${d}${h}`} className="border-b border-r border-slate-200 bg-slate-50 text-center text-slate-500">
              {FIRST_HOUR + h}-{FIRST_HOUR + h + 1}
            </div>
          )),
        )}
      </div>

      {entities.map((entity) =>
        lines(entity.cells).map((line, n) => (
          <div key={`${entity.id}-${n}`} className="grid min-w-[110rem]" style={{ gridTemplateColumns: columns }}>
            <div className={clsx('sticky left-0 z-10 border-b border-r border-slate-300 bg-white px-2 py-1 font-medium', n > 0 && 'text-transparent')}
              style={{ gridRow: 1 }} role="rowheader">
              {entity.label}
              {view === 'room' && entity.capacity != null && n === 0 && (
                <span className="block font-normal text-slate-500">{entity.capacity} seats</span>
              )}
            </div>
            {Array.from({ length: DAYS.length * HOURS }, (_, slot) => (
              <div key={slot} style={{ gridColumn: slot + 2, gridRow: 1 }}
                className={clsx('min-h-12 border-b border-r border-slate-100', slot % HOURS === 0 && 'border-l border-l-slate-300',
                  over === `${entity.id}-${n}-${slot}` && 'bg-emerald-100')}
                onDragOver={editable ? (e) => { e.preventDefault(); setOver(`${entity.id}-${n}-${slot}`) } : undefined}
                onDragLeave={editable ? () => setOver(null) : undefined}
                onDrop={editable ? (e) => drop(e, slot) : undefined}
                aria-label={`${entity.label} ${slotDay(slot)} ${slotHour(slot)}:00`}
              />
            ))}
            {line.map((cell) => (
              <button key={cell.key} type="button" draggable={editable}
                onDragStart={(e) => { e.dataTransfer.setData('text/session-key', cell.key); e.dataTransfer.effectAllowed = 'move' }}
                onClick={() => onSelect(cell)}
                style={{ gridColumn: `${cell.start_slot + 2} / span ${cell.length}`, gridRow: 1 }}
                className={clsx('relative z-0 m-0.5 rounded border px-1 py-0.5 text-left leading-tight shadow-sm',
                  cell.pinned ? 'border-amber-400 bg-amber-50' : 'border-emerald-300 bg-emerald-50',
                  highlight?.has(cell.key) && 'ring-2 ring-red-500',
                  editable && 'cursor-grab active:cursor-grabbing')}
                title={`${cell.unit_code} ${cell.group} ${cell.room} ${cell.day} ${cell.start_time}-${cell.end_time}`}>
                <span className="block font-semibold">{cell.unit_code}</span>
                {cell.group && <span className="block">{cell.group}</span>}
                {view !== 'room' && <span className="block text-slate-600">{cell.room}</span>}
                {cell.pinned && <Pin size={10} className="absolute right-0.5 top-0.5 text-amber-600" aria-label="pinned" />}
              </button>
            ))}
          </div>
        )),
      )}
      {entities.length === 0 && <p className="p-4 text-slate-500">Nothing to show.</p>}
    </div>
  )
}
