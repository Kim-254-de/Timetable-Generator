import { useState } from 'react'
import { FileUp } from 'lucide-react'
import { errorMessage } from '@/lib/api'
import {
  useDeleteHealthPaper,
  useReadHealthList,
  useRecountHealthPapers,
  useSaveHealthList,
  useSetHealthRows,
  type HealthRowInput,
} from '@/lib/queries'
import type { ExamPaperItem, HealthListReview } from '@/lib/types'

const DOCX = '.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const input = 'rounded-md border border-line px-2 py-1'

interface Draft { include: boolean; codes: string; title: string; sitting: 'regular' | 'odel' }
const splitCodes = (codes: string) => codes.split('/').map((c) => c.trim()).filter(Boolean)

function UploadReview({ termId, review, onDone }: { termId: string; review: HealthListReview; onDone: () => void }) {
  const save = useSaveHealthList(termId)
  const [drafts, setDrafts] = useState<Draft[]>(
    review.entries.map((e) => ({ include: e.duplicate_of === null, codes: e.codes.join('/'), title: e.title, sitting: e.sitting })),
  )
  const chosen = drafts.filter((d) => d.include && splitCodes(d.codes).length > 0)
  const set = (i: number, patch: Partial<Draft>) => setDrafts(drafts.map((d, j) => (j === i ? { ...d, ...patch } : d)))
  return (
    <div className="space-y-2">
      <p className="text-muted">
        {review.summary.papers} papers read{review.summary.duplicates > 0 && `, ${review.summary.duplicates} repeated rows left out`}. Check the notes, then save.
      </p>
      {!review.smarttt.available && (
        <p role="status" className="rounded-md bg-warning-soft px-3 py-2 text-warning">
          Classes couldn't be read from SMARTTT: {review.smarttt.reason} You can still save, and re-count later.
        </p>
      )}
      <div className="max-h-96 overflow-auto rounded-md border border-line">
        <table className="w-full text-left text-xs">
          <thead className="bg-surface text-muted">
            <tr><th className="px-2 py-1"><span className="sr-only">Include</span></th><th className="px-2 py-1">Codes</th><th className="px-2 py-1">Title</th><th className="px-2 py-1">Sitting</th><th className="px-2 py-1">Students</th><th className="px-2 py-1">Check</th></tr>
          </thead>
          <tbody>
            {review.entries.map((e, i) => {
              const d = drafts[i]
              const notes = [
                e.duplicate_of !== null && `Same as line ${e.duplicate_of}`,
                e.unknown_codes.length > 0 && `SMARTTT doesn't know ${e.unknown_codes.join(', ')}: check the code`,
                e.department_lists.length > 0 && `Listed by ${e.department_lists.join(', ')}: their paper is marked health, not entered again`,
                e.already_here && 'Already here: its title updates',
                e.students === 0 && e.classes.length > 0 && 'On the master timetable, nobody synced: enter the numbers after saving',
                e.students === 0 && e.classes.length === 0 && 'Not on the master timetable and nobody synced: add its classes after saving',
              ].filter((n): n is string => !!n)
              return (
                <tr key={e.line} className="border-t border-line align-top">
                  <td className="px-2 py-1"><input type="checkbox" checked={d.include} aria-label={`Include line ${e.line}`} onChange={(x) => set(i, { include: x.target.checked })} /></td>
                  <td className="px-2 py-1"><input value={d.codes} aria-label={`Codes, line ${e.line}`} onChange={(x) => set(i, { codes: x.target.value })} className={`${input} w-36`} /></td>
                  <td className="px-2 py-1"><input value={d.title} aria-label={`Title, line ${e.line}`} onChange={(x) => set(i, { title: x.target.value })} className={`${input} w-full min-w-40`} /></td>
                  <td className="px-2 py-1">
                    <select value={d.sitting} aria-label={`Sitting, line ${e.line}`} onChange={(x) => set(i, { sitting: x.target.value as Draft['sitting'] })} className={input}>
                      <option value="regular">Regular</option><option value="odel">ODEL</option>
                    </select>
                  </td>
                  <td className="px-2 py-1" title={e.classes.join('\n')}>
                    {e.students ?? '—'}{e.classes.length > 0 && <span className="block text-muted">{e.classes.length} class{e.classes.length > 1 ? 'es' : ''}</span>}
                  </td>
                  <td className="px-2 py-1 text-warning">{notes.map((n) => <span key={n} className="block">{n}</span>)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {save.isError && <p role="alert" className="text-danger">{errorMessage(save.error)}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onDone} className="rounded-md border border-line px-3 py-2">Cancel</button>
        <button type="button" disabled={chosen.length === 0 || save.isPending} className="rounded-md bg-brand px-4 py-2 text-white disabled:opacity-50"
          onClick={() => save.mutate(chosen.map((d) => ({ codes: splitCodes(d.codes), title: d.title.trim(), sitting: d.sitting })), { onSuccess: onDone })}>
          Save {chosen.length} papers
        </button>
      </div>
    </div>
  )
}

function Numbers({ termId, paper, onClose }: { termId: string; paper: ExamPaperItem; onClose: () => void }) {
  const save = useSetHealthRows(termId)
  const [rows, setRows] = useState<HealthRowInput[]>(paper.rows.map(({ programme, year, semester, stream, students }) => ({ programme, year, semester, stream, students })))
  const set = (i: number, patch: Partial<HealthRowInput>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  return (
    <div className="space-y-2 rounded-md border border-line p-3">
      <h3 className="font-semibold">Students sitting {paper.codes}</h3>
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2">
          <input aria-label="Programme" placeholder="Programme" value={r.programme} onChange={(e) => set(i, { programme: e.target.value })} className={`${input} w-32`} />
          <label>Year <input aria-label="Year" type="number" min={1} max={10} value={r.year} onChange={(e) => set(i, { year: Number(e.target.value) })} className={`${input} w-14`} /></label>
          <label>Sem <input aria-label="Semester" type="number" min={1} max={3} value={r.semester} onChange={(e) => set(i, { semester: Number(e.target.value) })} className={`${input} w-14`} /></label>
          <input aria-label="Stream" placeholder="Stream" value={r.stream} onChange={(e) => set(i, { stream: e.target.value })} className={`${input} w-20`} />
          <label>Students <input aria-label="Students" type="number" min={0} max={5000} value={r.students} onChange={(e) => set(i, { students: Number(e.target.value) })} className={`${input} w-20`} /></label>
          <button type="button" className="text-danger" onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      {rows.length === 0 && <p className="text-muted">No class yet. Add the classes that sit it.</p>}
      {save.isError && <p role="alert" className="text-danger">{errorMessage(save.error)}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="button" className="rounded-md border border-line px-3 py-1" onClick={() => setRows([...rows, { programme: '', year: 1, semester: 1, stream: '', students: 0 }])}>Add a class</button>
        <button type="button" disabled={save.isPending} className="rounded-md bg-brand px-3 py-1 text-white disabled:opacity-50"
          onClick={() => save.mutate({ paperId: paper.id, rows: rows.filter((r) => r.programme.trim()) }, { onSuccess: onClose })}>Save</button>
        <button type="button" className="rounded-md border border-line px-3 py-1" onClick={onClose}>Cancel</button>
      </div>
    </div>
  )
}

/**
 * The health and nursing moderation letter, uploaded by the Director rather than
 * a department. A general upload of other papers is to come.
 */
export function HealthPapers({ termId, papers }: { termId: string; papers: ExamPaperItem[] }) {
  const read = useReadHealthList(termId)
  const recount = useRecountHealthPapers(termId)
  const remove = useDeleteHealthPaper(termId)
  const [review, setReview] = useState<HealthListReview | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const mine = papers.filter((p) => p.director_paper).sort((a, b) => a.codes.localeCompare(b.codes))
  const noNumbers = mine.filter((p) => p.students === 0).length
  return (
    <section className="space-y-3 rounded-lg border border-line bg-card p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">Health and nursing papers</h2>
          <p className="text-muted">Upload their moderation letter (Word). These papers sit only in the health unit, in the first or last session of a day.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {mine.length > 0 && (
            <button type="button" disabled={recount.isPending} onClick={() => recount.mutate()} className="rounded-md border border-line px-3 py-2">Re-count</button>
          )}
          <label className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-brand px-3 py-2 text-white">
            <FileUp size={16} aria-hidden /> {read.isPending ? 'Reading…' : 'Upload the letter'}
            <input type="file" accept={DOCX} className="sr-only" disabled={read.isPending}
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (file) read.mutate(file, { onSuccess: setReview })
              }} />
          </label>
        </div>
      </div>
      {read.isError && <p role="alert" className="text-danger">{errorMessage(read.error)}</p>}
      {recount.isSuccess && !recount.data.available && <p role="status" className="text-warning">SMARTTT couldn't be read: {recount.data.reason}</p>}
      {review && <UploadReview termId={termId} review={review} onDone={() => setReview(null)} />}
      {noNumbers > 0 && <p className="text-warning">{noNumbers} of these papers have no student number yet: they get a date, and a room once they have one.</p>}
      {remove.isError && <p role="alert" className="text-danger">{errorMessage(remove.error)}</p>}
      {mine.length > 0 && (
        <ul className="max-h-72 overflow-y-auto">
          {mine.map((p) => (
            <li key={p.id} className="border-b border-line py-1 last:border-0">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span><b>{p.codes}</b> {p.title} <span className="text-muted">· {p.rows.length} class{p.rows.length === 1 ? '' : 'es'}</span></span>
                <span className="flex items-center gap-3">
                  <button type="button" onClick={() => setEditing(editing === p.id ? null : p.id)} className="text-brand-ink">{p.students} students</button>
                  <button type="button" className="text-danger" onClick={() => { if (window.confirm(`Remove ${p.codes}?`)) remove.mutate(p.id) }}>Remove</button>
                </span>
              </div>
              {editing === p.id && <Numbers termId={termId} paper={p} onClose={() => setEditing(null)} />}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
