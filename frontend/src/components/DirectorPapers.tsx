import { useDeleteDirectorPaper } from '@/lib/queries'
import { errorMessage } from '@/lib/api'
import type { ExamPaperItem } from '@/lib/types'

/**
 * Papers the Director uploaded before departments did it for health and nursing.
 * Each stays an ordinary paper until it is removed or a department lists its unit.
 */
export function DirectorPapers({ termId, papers }: { termId: string; papers: ExamPaperItem[] }) {
  const remove = useDeleteDirectorPaper(termId)
  const mine = papers.filter((p) => p.director_paper).sort((a, b) => a.codes.localeCompare(b.codes))
  if (mine.length === 0) return null
  return (
    <section className="space-y-3 rounded-lg border border-line bg-card p-4 text-sm">
      <div>
        <h2 className="font-semibold">Papers you uploaded earlier</h2>
        <p className="text-muted">Health and nursing departments now upload their moderation letters in Smart Attendance like any other department. Each of these stays until you remove it, or a department lists its unit.</p>
      </div>
      {remove.isError && <p role="alert" className="text-danger">{errorMessage(remove.error)}</p>}
      <ul className="max-h-72 overflow-y-auto">
        {mine.map((p) => (
          <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-line py-1 last:border-0">
            <span><b>{p.codes}</b> {p.title} <span className="text-muted">· {p.category} · {p.students} students</span></span>
            <button type="button" className="text-danger" onClick={() => { if (window.confirm(`Remove ${p.codes}?`)) remove.mutate(p.id) }}>Remove</button>
          </li>
        ))}
      </ul>
    </section>
  )
}
