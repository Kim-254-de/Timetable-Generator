import clsx from 'clsx'
import { errorMessage } from '@/lib/api'
import { dateTime } from '@/lib/format'
import { useDepartmentStatus, useImportDepartments } from '@/lib/queries'
import type { ImportChanges, ImportResult } from '@/lib/types'

const changeText = (c: ImportChanges) =>
  [
    c.added.length && `${c.added.length} added (${c.added.join(', ')})`,
    c.changed.length && `${c.changed.length} changed (${c.changed.join(', ')})`,
    c.removed.length && `${c.removed.length} removed (${c.removed.join(', ')})`,
  ].filter(Boolean).join('; ') || 'no changes'

/**
 * Departments enter their courses, units, groups and lecturers in the
 * Teaching page in Smart Attendance and publish them; the Director imports what is published here.
 * A department that hasn't published can be imported later; the timetable can
 * then be re-solved keeping the published classes where they are.
 */
export function DepartmentSubmissions({ termId }: { termId: string }) {
  const status = useDepartmentStatus(termId)
  const run = useImportDepartments(termId)

  return (
    <div className="space-y-4">
      <section className="space-y-3 p-5 rounded-2xl bg-card shadow-[0_1px_3px_rgba(18,48,95,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold">Departments' teaching</h2>
            <p className="text-sm text-muted">
              What departments published from their Teaching page in Smart Attendance.
            </p>
          </div>
          <button onClick={() => run.mutate()} disabled={run.isPending || !status.data?.published}
            className="inline-flex h-11 px-5 cursor-pointer items-center justify-center gap-2 rounded-xl text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 bg-brand text-white shadow-sm hover:bg-brand-strong">
            {run.isPending ? 'Importing…' : `Import published departments${status.data?.needs_import ? ` (${status.data.needs_import} new)` : ''}`}
          </button>
        </div>
        {status.isPending && <p className="text-sm text-muted">Asking Smart Attendance…</p>}
        {status.isError && <p role="alert" className="text-sm text-danger">{errorMessage(status.error)}</p>}
        {run.isError && <p role="alert" className="text-sm text-danger">{errorMessage(run.error)}</p>}
        {run.isSuccess && <ImportSummary result={run.data} />}
        {status.data && (
          <>
            <p className="text-sm">
              {status.data.published} of {status.data.departments.length} departments have published.
              {status.data.not_published > 0 && ' You can generate without the others and add them when they publish.'}
            </p>
            <div className="overflow-x-auto rounded-xl border border-line">
              <table className="w-full text-left text-sm">
                <thead className="bg-surface text-xs uppercase text-muted">
                  <tr>
                    <th className="px-3 py-2">Department</th><th className="px-3 py-2">Published</th>
                    <th className="px-3 py-2">Units</th><th className="px-3 py-2">Imported</th>
                  </tr>
                </thead>
                <tbody>
                  {status.data.departments.map((d) => (
                    <tr key={d.code} className={clsx('border-t border-line', !d.published && 'text-muted')}>
                      <td className="px-3 py-2"><b>{d.code}</b> · {d.name}</td>
                      <td className="px-3 py-2">
                        {d.published && d.published_at ? (
                          <span className="text-success">{dateTime(d.published_at)}{d.published_by ? ` by ${d.published_by}` : ''}</span>
                        ) : d.reopened_at ? (
                          <span className="text-warning">
                            Reopened {dateTime(d.reopened_at)}
                            {d.changed_units?.length ? `; changed since: ${d.changed_units.join(', ')}` : ''}
                          </span>
                        ) : 'Not yet'}
                      </td>
                      <td className="px-3 py-2">{d.units ?? '—'}</td>
                      <td className="px-3 py-2">
                        {d.imported_at ? dateTime(d.imported_at) : '—'}
                        {d.needs_import && <span className="ml-2 rounded bg-warning-soft px-1 text-xs text-warning">import the new version</span>}
                      </td>
                    </tr>
                  ))}
                  {status.data.departments.length === 0 && (
                    <tr><td colSpan={4} className="px-3 py-6 text-center text-muted">No departments in Smart Attendance yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
      <details className="text-xs text-muted">
        <summary className="cursor-pointer">ⓘ A department published after you did?</summary>
        <p className="mt-1">Copy the published draft, tick “Keep the published classes” and re-solve: its classes are added and none of the published ones move.</p>
      </details>
    </div>
  )
}

function ImportSummary({ result }: { result: ImportResult }) {
  return (
    <div role="status" className="rounded-xl bg-success-soft px-3 py-2 text-sm text-success">
      <p>Imported {result.departments.join(', ')}. Class rows: {changeText(result.class_rows)}.</p>
      {Object.entries(result.units).map(([code, c]) => <p key={code}>{code} units: {changeText(c)}.</p>)}
      {result.not_published.length > 0 && (
        <p className="text-warning">Not published yet: {result.not_published.map((d) => d.code).join(', ')}.</p>
      )}
    </div>
  )
}
