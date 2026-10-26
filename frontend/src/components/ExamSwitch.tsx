import { useState } from 'react'
import clsx from 'clsx'
import { errorMessage } from '@/lib/api'
import { useExamSwitch, useExamSwitchAction } from '@/lib/queries'
import type { ExamSwitchAction } from '@/lib/types'

/** "2026-11-23T00:00:00+03:00" -> the value a datetime-local input shows (campus time). */
const local = (iso: string | null) => (iso ? iso.slice(0, 16) : '')
const withZone = (value: string) => (value ? `${value}:00+03:00` : undefined)

/**
 * Switching SMARTTT from teaching to exams for everyone at once, and closing
 * the exam period: scheduled, moved, cancelled or done now. Times are campus time.
 */
export function ExamSwitch({ termId }: { termId: string }) {
  const state = useExamSwitch(termId)
  const act = useExamSwitchAction(termId)
  const [switchAt, setSwitchAt] = useState('')
  const [closeAt, setCloseAt] = useState('')

  if (state.isPending) return null
  if (state.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(state.error)}</p>
  const s = state.data
  const run = (action: ExamSwitchAction, at?: string, confirm?: string) => {
    if (confirm && !window.confirm(confirm)) return
    act.mutate({ action, ...(at ? { at } : {}) })
  }

  return (
    <section className="space-y-3 rounded-lg border border-line bg-card p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">Switch SMARTTT to exams</h2>
          <p className="text-muted">
            From the switch, students and lecturers see only their exams in SMARTTT: the teaching timetable is hidden,
            and attendance takes exam sessions only.
          </p>
        </div>
        <span className={clsx('rounded px-2 py-1 text-xs font-medium',
          s.status === 'switched' ? 'bg-success-soft text-success' : s.status === 'scheduled' ? 'bg-brand-soft text-brand-ink' : 'bg-surface text-muted')}>
          {s.label}
        </span>
      </div>
      {!s.in_smarttt && <p className="text-warning">This term exists only in the Generator, so SMARTTT can't be switched.</p>}
      {s.in_smarttt && s.published_version == null && <p className="text-warning">Publish an exam timetable first.</p>}
      {s.smarttt_reachable === false && <p className="text-warning">SMARTTT can't be reached; this is the state it last confirmed.</p>}
      {s.in_smarttt && s.published_version != null && s.status !== 'closed' && (
        <div className="grid gap-4 md:grid-cols-2">
          {s.status !== 'switched' && (
            <div className="space-y-2">
              <label className="block">Switch on (campus time)
                <input type="datetime-local" value={switchAt || local(s.switch_at ?? s.defaults.switch_at)} onChange={(e) => setSwitchAt(e.target.value)}
                  className="mt-1 block rounded-md border border-line px-2 py-1" />
              </label>
              <div className="flex flex-wrap gap-2">
                <button onClick={() => run('schedule_switch', withZone(switchAt || local(s.switch_at ?? s.defaults.switch_at)))} disabled={act.isPending}
                  className="rounded-md bg-brand px-3 py-2 text-white disabled:opacity-50">{s.switch_at ? 'Move the switch' : 'Schedule the switch'}</button>
                {s.switch_at && <button onClick={() => run('cancel_switch')} disabled={act.isPending} className="rounded-md border border-line px-3 py-2">Cancel it</button>}
                <button onClick={() => run('switch_now', undefined, 'Switch SMARTTT to exams now, for everyone?')} disabled={act.isPending}
                  className="rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-warning">Switch now</button>
              </div>
            </div>
          )}
          {s.status !== 'teaching' && (
            <div className="space-y-2">
              <label className="block">Close the exam period on (campus time)
                <input type="datetime-local" value={closeAt || local(s.close_at ?? s.defaults.close_at)} onChange={(e) => setCloseAt(e.target.value)}
                  className="mt-1 block rounded-md border border-line px-2 py-1" />
              </label>
              <div className="flex flex-wrap gap-2">
                <button onClick={() => run('schedule_close', withZone(closeAt || local(s.close_at ?? s.defaults.close_at)))} disabled={act.isPending}
                  className="rounded-md border border-line px-3 py-2">{s.close_at ? 'Move the close' : 'Schedule the close'}</button>
                {s.close_at && <button onClick={() => run('cancel_close')} disabled={act.isPending} className="rounded-md border border-line px-3 py-2">Cancel it</button>}
                <button onClick={() => run('close_now', undefined, 'Close the exam period now? SMARTTT goes back to the teaching timetable.')} disabled={act.isPending}
                  className="rounded-md border border-line px-3 py-2">Close now</button>
              </div>
              <p className="text-xs text-muted">The exam period also closes on its own when the next term's teaching timetable is published.</p>
            </div>
          )}
        </div>
      )}
      {act.isError && <p role="alert" className="text-danger">{errorMessage(act.error)}</p>}
    </section>
  )
}
