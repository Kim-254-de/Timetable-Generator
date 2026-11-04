import { useState, type FormEvent } from 'react'
import { BulkPaste, type BulkColumn } from '@/components/BulkPaste'
import { Dialog, Field, inputClass } from '@/components/Dialog'
import { errorMessage } from '@/lib/api'
import { useBulkDepartments, useDeleteDepartment, useDepartmentList, useSaveDepartment, useSyncDepartments, type DepartmentInput } from '@/lib/queries'
import type { Department } from '@/lib/types'

const COLUMNS: BulkColumn[] = [
  { key: 'department', label: 'Department', example: 'Computer Science', required: true,
    hint: 'Its name or code, as on the Departments list.' },
  { key: 'code', label: 'Code', example: 'DCOMP', hint: 'Optional, only for a department Attendance gives no code: the code printed on the timetable.' },
  { key: 'lecturer_count', label: 'Lecturers', example: '24',
    hint: 'How many lecturers the department has. The Generator never runs more of its classes at once. Leave blank to keep the current number.' },
]

/**
 * Departments own units; the department that owns a unit allocates its
 * lecturer in Smart Attendance's department portal. An administrator creates each department in
 * Smart Attendance with a name and a code; both are read from there. The
 * Generator keeps its own lecturer count for each, and makes a code only for
 * a department Attendance has none for.
 */
export function DepartmentsPage() {
  const list = useDepartmentList()
  const sync = useSyncDepartments()
  const remove = useDeleteDepartment()
  const bulk = useBulkDepartments()
  const [editing, setEditing] = useState<Department | null>(null)
  const [pasting, setPasting] = useState(false)
  const report = sync.data?.report

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Departments</h1>
          <p className="text-sm text-muted">
            From Smart Attendance, where an administrator adds each one with its code. Set each one’s number of lecturers here. Used by every term.
          </p>
        </div>
        <div className="flex gap-2 text-sm">
          <button onClick={() => setPasting(true)} className="rounded-md border border-line bg-card px-3 py-2">Paste lecturer numbers</button>
          {list.data?.attendance_connected && (
            <button onClick={() => sync.mutate()} disabled={sync.isPending} className="rounded-md bg-brand px-3 py-2 text-white disabled:opacity-50">
              {sync.isPending ? 'Refreshing…' : 'Refresh from Attendance'}
            </button>
          )}
        </div>
      </div>
      {list.data && !list.data.attendance_connected && (
        <p role="status" className="rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">
          Smart Attendance is not connected (ATTENDANCE_BASE_URL), so these are the departments as last read.
        </p>
      )}
      {report && (
        <p role="status" className="rounded-md bg-success-soft px-3 py-2 text-sm text-success">
          Up to date with Attendance: {report.created} added, {report.linked} linked, {report.updated} updated.
          {report.skipped.length > 0 && ` ${report.skipped.join(' ')}`}
        </p>
      )}
      {(list.isError || remove.isError || sync.isError) && (
        <p role="alert" className="text-sm text-danger">{errorMessage(list.error ?? remove.error ?? sync.error)}</p>
      )}
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr><th className="px-3 py-2">Code</th><th className="px-3 py-2">Name</th><th className="px-3 py-2">Lecturers</th><th /></tr>
          </thead>
          <tbody>
            {(list.data?.departments ?? []).map((d) => (
              <tr key={d.id} className="border-t border-line">
                <td className="px-3 py-2 font-medium">
                  {d.code}
                  {!d.code_from_attendance && d.from_attendance && <span className="ml-2 rounded bg-warning-soft px-1.5 py-0.5 text-xs text-warning">no code in Attendance</span>}
                </td>
                <td className="px-3 py-2">
                  {d.name}
                  {!d.from_attendance && <span className="ml-2 rounded bg-warning-soft px-1.5 py-0.5 text-xs text-warning">not in Attendance</span>}
                </td>
                <td className="px-3 py-2">
                  {d.lecturer_count ?? <span className="text-muted">no limit</span>}
                  {d.attendance_lecturer_count != null && <span className="ml-2 text-xs text-muted">({d.attendance_lecturer_count} in Attendance)</span>}
                </td>
                <td className="space-x-3 px-3 py-2 text-right">
                  <button onClick={() => setEditing(d)} className="text-brand-ink">Edit</button>
                  {!d.from_attendance && (
                    <button onClick={() => { if (window.confirm(`Delete ${d.code}?`)) remove.mutate(d.id) }} className="text-danger">Delete</button>
                  )}
                </td>
              </tr>
            ))}
            {list.data?.departments.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-6 text-center text-muted">No departments yet. An administrator adds them in Smart Attendance.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {editing && <DepartmentForm department={editing} onClose={() => setEditing(null)} />}
      {pasting && (
        <BulkPaste title="Paste lecturer numbers" columns={COLUMNS} templateName="department-lecturers.csv"
          submit={(rows) => bulk.mutateAsync(rows)} onClose={() => setPasting(false)} />
      )}
    </div>
  )
}

function DepartmentForm({ department, onClose }: { department: Department; onClose: () => void }) {
  const save = useSaveDepartment()
  const [form, setForm] = useState<DepartmentInput>({ code: department.code, lecturer_count: department.lecturer_count })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    // An empty count is sent as 0, which clears it.
    save.mutate({ id: department.id, body: { ...form, lecturer_count: form.lecturer_count ?? 0 } }, { onSuccess: onClose })
  }
  return (
    <Dialog title={`Edit ${department.name}`} onClose={onClose}>
      <form onSubmit={submit} className="mt-3 space-y-3">
        <p className="text-sm text-muted">
          The name{department.code_from_attendance ? ' and code come' : ' comes'} from Smart Attendance and {department.code_from_attendance ? 'are' : 'is'} changed there.
        </p>
        <Field label="Code" hint={department.code_from_attendance ? 'Set in Smart Attendance’s admin console.' : 'Printed on the timetable and how its published teaching names it. Attendance has no code for this department yet.'}>
          <input required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="DCOMP"
            disabled={department.code_from_attendance} className={inputClass} />
        </Field>
        <Field label="Number of lecturers" hint={`The Generator never runs more of this department's classes at the same hour. Leave blank for no limit.${department.attendance_lecturer_count != null ? ` Attendance lists ${department.attendance_lecturer_count}.` : ''}`}>
          <input type="number" min={1} value={form.lecturer_count ?? ''}
            onChange={(e) => setForm({ ...form, lecturer_count: e.target.value === '' ? null : Number(e.target.value) })} className={inputClass} />
        </Field>
        {save.isError && <p role="alert" className="text-sm text-danger">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-2 text-sm">Cancel</button>
          <button type="submit" disabled={save.isPending} className="rounded-md bg-brand px-4 py-2 text-sm text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </Dialog>
  )
}
