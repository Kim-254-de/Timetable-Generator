import clsx from 'clsx'
import { Download } from 'lucide-react'
import { Card, PanelButton, Pill, btn } from '@/components/ui'
import { errorMessage } from '@/lib/api'
import { dateTime } from '@/lib/format'
import { useDepartmentStatus, useImportDepartments } from '@/lib/queries'
import type { DepartmentStatus, ImportChanges, ImportResult } from '@/lib/types'

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
  const data = status.data
  const total = data?.departments.length ?? 0
  const share = total ? Math.round(((data?.published ?? 0) / total) * 100) : 0

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center gap-8">
          <div className="min-w-0 flex-1 basis-80 space-y-3">
            <h2 className="text-lg font-semibold">Departments' teaching</h2>
            {status.isPending && <p className="text-sm text-muted">Asking Smart Attendance…</p>}
            {status.isError && <p role="alert" className="text-sm text-danger">{errorMessage(status.error)}</p>}
            {data && (
              <>
                <p className="flex items-baseline gap-2">
                  <span className="text-5xl font-bold tracking-tight text-brand-ink">{data.published}</span>
                  <span className="text-lg text-muted">of {total} have published</span>
                </p>
                <div className="h-2.5 overflow-hidden rounded-full bg-brand-soft" aria-hidden>
                  <div className="h-full rounded-full bg-brand" style={{ width: `${share}%` }} />
                </div>
              </>
            )}
            <p className="text-sm text-muted">Departments publish from their Teaching page in Smart Attendance.
              {data && data.not_published > 0 && ' You can generate without the others and add them when they publish.'}</p>
          </div>
          <div className="flex flex-1 basis-56 flex-col gap-2 sm:max-w-xs">
            <button type="button" onClick={() => run.mutate()} disabled={run.isPending || !data?.published} className={clsx(btn.primary, 'py-3 text-base')}>
              <Download className="size-5" aria-hidden />
              {run.isPending ? 'Importing…' : data?.needs_import ? `Import ${data.needs_import} new` : 'Import published'}
            </button>
            <PanelButton label="See each department" title="Departments' teaching" wide>
              {data && <DepartmentTable departments={data.departments} />}
              <p className="text-sm text-muted">
                A department imported after publishing: open the published draft, copy it to a new draft, tick
                “Keep the published classes” and re-solve. Its classes are added without moving the published ones.
              </p>
            </PanelButton>
          </div>
        </div>
      </Card>
      {run.isError && <p role="alert" className="text-sm text-danger">{errorMessage(run.error)}</p>}
      {run.isSuccess && <ImportSummary result={run.data} />}
    </div>
  )
}

function DepartmentTable({ departments }: { departments: DepartmentStatus['departments'] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full text-left text-sm">
        <thead className="bg-surface text-xs uppercase text-muted">
          <tr>
            <th className="px-3 py-2">Department</th><th className="px-3 py-2">Published</th>
            <th className="px-3 py-2">Units</th><th className="px-3 py-2">Imported</th>
          </tr>
        </thead>
        <tbody>
          {departments.map((d) => (
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
                ) : <Pill tone="warning">Not yet</Pill>}
              </td>
              <td className="px-3 py-2">{d.units ?? '—'}</td>
              <td className="px-3 py-2">
                {d.imported_at ? dateTime(d.imported_at) : '—'}
                {d.needs_import && <span className="ml-2"><Pill tone="warning">import the new version</Pill></span>}
              </td>
            </tr>
          ))}
          {departments.length === 0 && (
            <tr><td colSpan={4} className="px-3 py-6 text-center text-muted">No departments in Smart Attendance yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function ImportSummary({ result }: { result: ImportResult }) {
  return (
    <div role="status" className="space-y-1 rounded-lg bg-success-soft px-4 py-3 text-sm text-success">
      <p>Imported {result.departments.join(', ')}. Class rows: {changeText(result.class_rows)}.</p>
      {Object.entries(result.units).map(([code, c]) => <p key={code}>{code} units: {changeText(c)}.</p>)}
      {result.not_published.length > 0 && (
        <p className="text-warning">Not published yet: {result.not_published.map((d) => d.code).join(', ')}.</p>
      )}
    </div>
  )
}
