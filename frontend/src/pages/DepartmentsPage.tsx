import { useState, type FormEvent } from 'react'
import { BulkPaste, type BulkColumn } from '@/components/BulkPaste'
import { Dialog, Field, inputClass } from '@/components/Dialog'
import { errorMessage } from '@/lib/api'
import { useBulkDepartments, useDeleteDepartment, useDepartments, useSaveDepartment, type DepartmentInput } from '@/lib/queries'
import type { Department } from '@/lib/types'

const COLUMNS: BulkColumn[] = [
  { key: 'code', label: 'Code', example: 'DCOMP', required: true },
  { key: 'name', label: 'Name', example: 'Department of Computer Science and ICT', required: true },
  { key: 'school', label: 'School', example: 'School of Science and Technology' },
  { key: 'lecturer_count', label: 'Lecturers', example: '24',
    hint: 'How many lecturers the department has. The Generator never runs more of its classes at once. Leave blank for no limit.' },
]

/** Departments own units; the department that owns a unit allocates its lecturer in the Allocator. */
export function DepartmentsPage() {
  const departments = useDepartments()
  const remove = useDeleteDepartment()
  const bulk = useBulkDepartments()
  const [editing, setEditing] = useState<Department | 'new' | null>(null)
  const [pasting, setPasting] = useState(false)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Departments</h1>
          <p className="text-sm text-slate-600">Each unit belongs to one department. Used by every term.</p>
        </div>
        <div className="flex gap-2 text-sm">
          <button onClick={() => setPasting(true)} className="rounded-md border border-slate-300 bg-white px-3 py-2">Paste from Excel</button>
          <button onClick={() => setEditing('new')} className="rounded-md bg-emerald-700 px-3 py-2 text-white">+ Add a department</button>
        </div>
      </div>
      {(departments.isError || remove.isError) && <p role="alert" className="text-sm text-red-700">{errorMessage(departments.error ?? remove.error)}</p>}
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr><th className="px-3 py-2">Code</th><th className="px-3 py-2">Name</th><th className="px-3 py-2">School</th><th className="px-3 py-2">Lecturers</th><th /></tr>
          </thead>
          <tbody>
            {(departments.data ?? []).map((d) => (
              <tr key={d.id} className="border-t border-slate-100">
                <td className="px-3 py-2 font-medium">{d.code}</td>
                <td className="px-3 py-2">{d.name}</td>
                <td className="px-3 py-2 text-slate-600">{d.school}</td>
                <td className="px-3 py-2">{d.lecturer_count ?? <span className="text-slate-400">no limit</span>}</td>
                <td className="space-x-3 px-3 py-2 text-right">
                  <button onClick={() => setEditing(d)} className="text-emerald-700">Edit</button>
                  <button onClick={() => { if (window.confirm(`Delete ${d.code}?`)) remove.mutate(d.id) }} className="text-red-700">Delete</button>
                </td>
              </tr>
            ))}
            {departments.data?.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-500">No departments yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {editing && <DepartmentForm department={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {pasting && (
        <BulkPaste title="Paste departments" columns={COLUMNS} templateName="departments.csv"
          submit={(rows) => bulk.mutateAsync(rows)} onClose={() => setPasting(false)} />
      )}
    </div>
  )
}

function DepartmentForm({ department, onClose }: { department: Department | null; onClose: () => void }) {
  const save = useSaveDepartment()
  const [form, setForm] = useState<DepartmentInput>({
    code: department?.code ?? '',
    name: department?.name ?? '',
    school: department?.school ?? '',
    lecturer_count: department?.lecturer_count ?? null,
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    // Editing: an empty count is sent as 0, which clears it.
    const body = { ...form, lecturer_count: form.lecturer_count ?? (department ? 0 : null) }
    save.mutate({ id: department?.id, body }, { onSuccess: onClose })
  }
  return (
    <Dialog title={department ? `Edit ${department.code}` : 'Add a department'} onClose={onClose}>
      <form onSubmit={submit} className="mt-3 space-y-3">
        <div className="grid grid-cols-3 gap-3">
          <Field label="Code"><input required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="DCOMP" className={inputClass} /></Field>
          <div className="col-span-2">
            <Field label="Name"><input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputClass} /></Field>
          </div>
        </div>
        <Field label="School"><input value={form.school} onChange={(e) => setForm({ ...form, school: e.target.value })} className={inputClass} /></Field>
        <Field label="Number of lecturers" hint="The Generator never runs more of this department's classes at the same hour. Leave blank for no limit.">
          <input type="number" min={1} value={form.lecturer_count ?? ''}
            onChange={(e) => setForm({ ...form, lecturer_count: e.target.value === '' ? null : Number(e.target.value) })} className={inputClass} />
        </Field>
        {save.isError && <p role="alert" className="text-sm text-red-700">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-slate-300 px-3 py-2 text-sm">Cancel</button>
          <button type="submit" disabled={save.isPending} className="rounded-md bg-emerald-700 px-4 py-2 text-sm text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </Dialog>
  )
}
