import { useState } from 'react'
import clsx from 'clsx'
import { FileUp } from 'lucide-react'
import { inputClass } from '@/components/Dialog'
import { Notice, btn } from '@/components/ui'
import { errorMessage } from '@/lib/api'
import { readExamLetter, useDepartments, useSaveExamLetter } from '@/lib/queries'
import type { ExamLetterPaper, ExamLetterReview } from '@/lib/types'

interface Draft { include: boolean; codes: string; title: string; sitting: 'regular' | 'odel'; switchFrom: boolean }
interface ClassDraft { use: boolean; programme: string; year: number; semester: number; students: number }

const splitCodes = (codes: string) => codes.split('/').map((c) => c.trim()).filter(Boolean)
const th = 'px-3 py-2 text-left text-xs font-medium text-muted'
const td = 'px-3 py-2 align-top'
const small = 'rounded-md border border-line px-2 py-1'

/**
 * A department's moderation letter uploaded on the Director's end. Smart Attendance reads and checks
 * it exactly as when the department uploads it (the same review, the same rules for ODEL papers,
 * duplicates and class numbers); saving puts the papers on the department's list there, publishes
 * it in the Director's name, and imports every published department's papers here.
 */
export function ExamLetterUpload({ termId, onDone }: { termId: string; onDone: () => void }) {
  const departments = useDepartments()
  const save = useSaveExamLetter(termId)
  const [department, setDepartment] = useState('')
  const [reading, setReading] = useState(false)
  const [readError, setReadError] = useState<unknown>(null)
  const [review, setReview] = useState<ExamLetterReview | null>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [classes, setClasses] = useState<Record<string, ClassDraft>>({})
  const name = departments.data?.find((d) => d.code === department)?.name ?? department

  const read = async (file: File | undefined) => {
    if (!file || !department) return
    setReading(true)
    setReadError(null)
    try {
      const r = await readExamLetter(termId, department, file)
      setReview(r)
      setDrafts(r.entries.map((e) => ({ include: e.duplicateOf === null, codes: e.codes.join('/'), title: e.title, sitting: e.sitting, switchFrom: !!e.switchesPaperId })))
      setClasses(Object.fromEntries(r.classes.map((c) => [c.id, { use: true, programme: c.programme, year: c.year ?? 1, semester: c.semester ?? 1, students: c.students }])))
    } catch (error) {
      setReadError(error)
    } finally {
      setReading(false)
    }
  }

  if (save.isSuccess) {
    const { saved, imported } = save.data
    return (
      <div className="space-y-4 text-sm">
        <Notice tone="success">
          {name}: {saved.created} papers added, {saved.updated} updated{saved.switched ? `, ${saved.switched} turned into ODEL papers` : ''}.
          Its list is published in your name, and the papers are imported: {imported.papers.added.length} new here, {imported.papers.changed.length} changed.
        </Notice>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => { save.reset(); setReview(null); setDrafts([]) }} className={btn.secondary}>Upload another letter</button>
          <button type="button" onClick={onDone} className={btn.primary}>Done</button>
        </div>
      </div>
    )
  }

  if (!review) {
    return (
      <div className="space-y-4 text-sm">
        <p className="text-muted">
          For a department that hasn't uploaded its letter. It is read and checked exactly as on the department's Exams tab in Smart Attendance:
          rows under an ODEL or part-time heading, or a unit's second listing, are ODEL papers, and a heading like “BSc Nursing Y1S1 (107 students)”
          sets that class's number. Saving adds the papers to the department's list, publishes it in your name, and imports them here.
          The department sees them on its Exams tab.
        </p>
        <label className="block">
          <span className="font-medium text-ink">Department</span>
          <select value={department} onChange={(e) => { setDepartment(e.target.value); setReadError(null) }} className={inputClass}>
            <option value="">Choose the department…</option>
            {departments.data?.map((d) => <option key={d.id} value={d.code}>{d.name} ({d.code})</option>)}
          </select>
        </label>
        <label className={clsx('flex flex-col items-center gap-2 rounded-xl border border-dashed border-line px-4 py-8 text-center',
          department ? 'cursor-pointer hover:bg-surface' : 'opacity-50')}>
          <FileUp className="size-6 text-brand-ink" aria-hidden />
          <span className="font-semibold text-ink">{reading ? 'Reading…' : department ? 'Choose the letter (.docx)' : 'Choose the department first'}</span>
          <input type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="sr-only"
            disabled={!department || reading} onChange={(e) => { void read(e.target.files?.[0]); e.target.value = '' }} />
        </label>
        {readError !== null && <p role="alert" className="text-danger">{errorMessage(readError)}</p>}
      </div>
    )
  }

  const chosen = drafts.filter((d) => d.include && splitCodes(d.codes).length > 0)
  const set = (i: number, patch: Partial<Draft>) => setDrafts(drafts.map((d, j) => (j === i ? { ...d, ...patch } : d)))
  const setClass = (id: string, patch: Partial<ClassDraft>) => setClasses({ ...classes, [id]: { ...classes[id]!, ...patch } })
  const unmatched = review.classes.filter((c) => classes[c.id]?.use && !classes[c.id]!.programme.trim()).length
  const submit = () => save.mutate({
    department_code: department,
    papers: chosen.map((d): ExamLetterPaper => {
      const entry = review.entries[drafts.indexOf(d)]
      const named = (entry?.letterClasses ?? []).flatMap((id) => {
        const c = classes[id]
        return c?.use && c.programme.trim() && c.students > 0 ? [{ programme: c.programme.trim(), year: c.year, semester: c.semester, students: c.students }] : []
      })
      return {
        codes: splitCodes(d.codes),
        title: d.title.trim(),
        sitting: d.sitting,
        ...(named.length ? { classes: named } : {}),
        ...(entry?.switchesPaperId && d.switchFrom && d.sitting === 'odel' ? { replacesPaperId: entry.switchesPaperId } : {}),
      }
    }),
  })

  return (
    <div className="space-y-4 text-sm">
      <p className="text-muted">
        <b className="text-ink">{name}</b>: {review.summary.papers} papers read
        {review.summary.newPapers < review.summary.papers && `, ${review.summary.papers - review.summary.newPapers} already on its list (their titles update)`}.
        {review.summary.secondListings > 0 && ` ${review.summary.secondListings} units listed twice: the second listing is the ODEL paper.`}
        {review.summary.toOdel > 0 && ` ${review.summary.toOdel} of its regular papers become ODEL papers.`}
        {review.summary.duplicates > 0 && ` ${review.summary.duplicates} repeated rows are left out.`}
        {' '}Check the highlighted rows, then save.
      </p>
      {!review.smarttt.available && (
        <Notice>Classes and student numbers couldn't be read from SMARTTT: {review.smarttt.reason} You can still save; numbers can be entered later.</Notice>
      )}

      {review.classes.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-semibold">Classes named in the letter</h3>
          <p className="text-muted">Each number goes on every paper under that class's heading.
            {unmatched > 0 && <span className="text-warning"> {unmatched} have no programme yet: choose one, or their numbers won't be saved.</span>}</p>
          <datalist id="letter-programmes">{review.programmes.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}</datalist>
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full min-w-[36rem]">
              <thead className="bg-surface"><tr><th className={th}>Use</th><th className={th}>Class in the letter</th><th className={th}>Programme</th><th className={th}>Year</th><th className={th}>Semester</th><th className={th}>Students</th></tr></thead>
              <tbody>
                {review.classes.map((c) => {
                  const d = classes[c.id]!
                  return (
                    <tr key={c.id} className="border-t border-line">
                      <td className={td}><input type="checkbox" checked={d.use} onChange={(e) => setClass(c.id, { use: e.target.checked })} aria-label={`Use ${c.name}`} /></td>
                      <td className={td} title={c.heading}>{c.name}</td>
                      <td className={clsx(td, !d.programme.trim() && 'bg-warning-soft')}><input list="letter-programmes" value={d.programme} onChange={(e) => setClass(c.id, { programme: e.target.value })} placeholder="Programme code" aria-label={`Programme of ${c.name}`} className={clsx(small, 'w-32')} /></td>
                      <td className={clsx(td, c.year === null && 'bg-warning-soft')}><input type="number" min={1} max={10} value={d.year} onChange={(e) => setClass(c.id, { year: Number(e.target.value) })} aria-label={`Year of ${c.name}`} className={clsx(small, 'w-16')} /></td>
                      <td className={clsx(td, c.semester === null && 'bg-warning-soft')}><input type="number" min={1} max={3} value={d.semester} onChange={(e) => setClass(c.id, { semester: Number(e.target.value) })} aria-label={`Semester of ${c.name}`} className={clsx(small, 'w-16')} /></td>
                      <td className={td}><input type="number" min={1} max={5000} value={d.students} onChange={(e) => setClass(c.id, { students: Number(e.target.value) })} aria-label={`Students of ${c.name}`} className={clsx(small, 'w-20')} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-[48rem]">
          <thead className="bg-surface">
            <tr><th className={th}><span className="sr-only">Include</span></th><th className={th}>Codes</th><th className={th}>Title</th><th className={th}>Sitting</th><th className={th}>Students</th><th className={th}>Check</th></tr>
          </thead>
          <tbody>
            {review.entries.map((e, i) => {
              const d = drafts[i]!
              const repeated = e.secondListingOf !== null ? review.entries.find((x) => x.line === e.secondListingOf) : undefined
              const notes = [
                e.duplicateOf !== null && `Same as line ${e.duplicateOf}`,
                repeated && `ODEL: second listing of line ${repeated.line}`,
                repeated && repeated.title.trim().toLowerCase() !== e.title.trim().toLowerCase() && `Title differs from line ${repeated.line} (“${repeated.title}”): check the code`,
                e.unknownCodes.length > 0 && `SMARTTT doesn't know ${e.unknownCodes.join(', ')}: check the code`,
                e.otherDepartments.length > 0 && `Also listed by ${e.otherDepartments.join(', ')}`,
                e.letterClasses.length === 0 && e.students === 0 && e.classRows.length > 0 && 'On the master timetable, nobody synced yet',
                e.letterClasses.length === 0 && e.students === 0 && e.classRows.length === 0 && 'Not on the master timetable and nobody synced',
                e.letterClasses.length > 0 && `Numbers from the letter's ${e.letterClasses.length === 1 ? 'class' : `${e.letterClasses.length} classes`}`,
                e.existingPaperId && 'Already on its list: updates it',
              ].filter((n): n is string => !!n)
              const warn = e.unknownCodes.length > 0 || e.otherDepartments.length > 0 || (e.letterClasses.length === 0 && e.students === 0 && e.classRows.length === 0)
              return (
                <tr key={e.line} className={clsx('border-t border-line', !d.include && 'opacity-50', warn && d.include && 'bg-warning-soft/60')}>
                  <td className={td}><input type="checkbox" checked={d.include} onChange={(x) => set(i, { include: x.target.checked })} aria-label={`Include line ${e.line}`} /></td>
                  <td className={td}>
                    <input value={d.codes} onChange={(x) => set(i, { codes: x.target.value })} aria-label={`Codes, line ${e.line}`} className={clsx(small, 'w-36')} />
                    {e.section && <span className="mt-0.5 block text-xs text-muted">{e.section}</span>}
                  </td>
                  <td className={td}><input value={d.title} onChange={(x) => set(i, { title: x.target.value })} aria-label={`Title, line ${e.line}`} className={clsx(small, 'min-w-44')} /></td>
                  <td className={td}>
                    <select value={d.sitting} onChange={(x) => set(i, { sitting: x.target.value as Draft['sitting'] })} aria-label={`Sitting, line ${e.line}`} className={small}>
                      <option value="regular">Regular</option><option value="odel">ODEL</option>
                    </select>
                  </td>
                  <td className={td} title={e.classRows.map((r) => `${r.label}: ${r.students}`).join('\n')}>
                    {e.students ?? '—'}
                    {e.classRows.length > 0 && <span className="block text-xs text-muted">{e.classRows.length} class{e.classRows.length > 1 ? 'es' : ''}</span>}
                  </td>
                  <td className={clsx(td, 'text-xs')}>
                    {notes.map((n) => <span key={n} className={clsx('block', /^(Already|Same|Numbers|ODEL)/.test(n) ? 'text-muted' : 'text-warning')}>{n}</span>)}
                    {!!e.switchesPaperId && d.sitting === 'odel' && (
                      <label className="mt-1 flex items-start gap-1.5 text-ink">
                        <input type="checkbox" checked={d.switchFrom} onChange={(x) => set(i, { switchFrom: x.target.checked })} className="mt-0.5" />
                        <span>Its regular paper becomes this ODEL paper, keeping its examiner and invigilators.</span>
                      </label>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {save.isError && <p role="alert" className="text-danger">{errorMessage(save.error)}</p>}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <button type="button" onClick={() => { setReview(null); setDrafts([]) }} className={clsx(btn.secondary, 'mr-auto')}>Another file</button>
        <button type="button" onClick={submit} disabled={chosen.length === 0 || save.isPending} className={btn.primary}>
          {save.isPending ? 'Saving and importing…' : `Save ${chosen.length} papers for ${department}`}
        </button>
      </div>
    </div>
  )
}
