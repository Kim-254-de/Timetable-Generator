import { useState } from 'react'
import { useRemoveDirectorPapers } from '@/lib/queries'
import { errorMessage } from '@/lib/api'
import type { ExamPaperItem } from '@/lib/types'

/**
 * Papers the Director uploaded before departments did it for health and nursing.
 * Each stays an ordinary paper until it is removed or a department lists its unit.
 */
export function DirectorPapers({ termId, papers }: { termId: string; papers: ExamPaperItem[] }) {
  const remove = useRemoveDirectorPapers(termId)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const mine = papers.filter((p) => p.director_paper).sort((a, b) => a.codes.localeCompare(b.codes))
  if (mine.length === 0) return null
  const chosen = mine.filter((p) => picked.has(p.id))
  const all = chosen.length === mine.length
  const toggle = (id: string) => {
    const next = new Set(picked)
    if (!next.delete(id)) next.add(id)
    setPicked(next)
  }
  const removeChosen = () => {
    const what = chosen.length === 1 ? chosen[0].codes : `these ${chosen.length} papers`
    if (!window.confirm(`Remove ${what}? They also leave any drafts they are on. This can't be undone.`)) return
    remove.mutate(chosen.map((p) => p.id), { onSuccess: () => setPicked(new Set()) })
  }
  return (
    <section className="space-y-3 p-5 text-sm rounded-2xl bg-card shadow-[0_1px_3px_rgba(18,48,95,0.08)]">
      <div>
        <h2 className="font-semibold">Papers you uploaded earlier</h2>
        <p className="text-muted">Health and nursing departments now upload their moderation letters in Smart Attendance like any other department. Each of these stays until you remove it, or a department lists its unit.</p>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={all} onChange={() => setPicked(all ? new Set() : new Set(mine.map((p) => p.id)))} />
          Select all {mine.length}
        </label>
        <button type="button" disabled={chosen.length === 0 || remove.isPending} onClick={removeChosen}
          className="inline-flex h-9 px-3 cursor-pointer items-center justify-center gap-2 rounded-xl text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 border border-danger-solid bg-card text-danger hover:bg-danger-solid hover:text-white">
          {remove.isPending ? 'Removing…' : `Remove selected (${chosen.length})`}
        </button>
      </div>
      {remove.isError && <p role="alert" className="text-danger">{errorMessage(remove.error)}</p>}
      <ul className="max-h-72 overflow-y-auto">
        {mine.map((p) => (
          <li key={p.id} className="border-b border-line py-1 last:border-0">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={picked.has(p.id)} onChange={() => toggle(p.id)} />
              <span><b>{p.codes}</b> {p.title} <span className="text-muted">· {p.category} · {p.students} students</span></span>
            </label>
          </li>
        ))}
      </ul>
    </section>
  )
}
