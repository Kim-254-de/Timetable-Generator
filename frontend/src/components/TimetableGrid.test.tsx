import { fireEvent, render, screen } from '@testing-library/react'
import { TimetableGrid } from './TimetableGrid'
import type { Cell, Entity } from '@/lib/types'

const cell = (key: string, start_slot: number, extra: Partial<Cell> = {}): Cell => ({
  key, unit_code: key.split('-')[0], group: '', room_id: 'r1', room: 'STB 1', day: 'MON', start_time: '07:00',
  end_time: '09:00', start_slot, length: 2, pinned: false, students: 50, ...extra,
})

const entities: Entity[] = [{
  id: 'row', label: 'BSC.COMP SCI Y1S1',
  cells: [cell('COSC103-GRA-1', 1, { group: 'GR A' }), cell('COSC110-MAIN-1', 1), cell('MATH101-MAIN-1', 20, { pinned: true })],
}]

describe('TimetableGrid', () => {
  it('lays sessions out across their hours and stacks parallel ones', () => {
    render(<TimetableGrid entities={entities} view="row" editable highlight={new Set()} onMove={() => {}} onSelect={() => {}} />)
    const first = screen.getByTitle(/COSC103 GR A STB 1/)
    expect(first).toHaveStyle({ gridColumn: '3 / span 2' })
    // Two classes at the same hour: two lines for the one class row.
    expect(screen.getAllByRole('rowheader')).toHaveLength(2)
    expect(screen.getByLabelText('pinned')).toBeInTheDocument()
  })

  it('reports a drop as a move to that hour', () => {
    const onMove = vi.fn()
    render(<TimetableGrid entities={entities} view="row" editable onMove={onMove} onSelect={() => {}} />)
    const target = screen.getAllByLabelText('BSC.COMP SCI Y1S1 TUE 10:00')[0]
    const data = { getData: () => 'MATH101-MAIN-1', setData: () => {}, effectAllowed: 'move' }
    fireEvent.drop(target, { dataTransfer: data })
    expect(onMove).toHaveBeenCalledWith('MATH101-MAIN-1', 15)
  })

  it('is read-only for published drafts', () => {
    render(<TimetableGrid entities={entities} view="row" editable={false} onMove={() => {}} onSelect={() => {}} />)
    expect(screen.getByTitle(/COSC103 GR A/)).toHaveAttribute('draggable', 'false')
  })
})
