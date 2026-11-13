import { useDepartmentStatus, useExams, useTerm } from './queries'

/**
 * A term is worked through in steps, teaching and exams each their own. A step is done when what it
 * makes exists; the step to work on is the first one not done (the last one once all are).
 */
export type Mode = 'teaching' | 'exams'

export const STEPS: Record<Mode, { key: string; label: string }[]> = {
  teaching: [
    { key: 'details', label: 'Term details' },
    { key: 'departments', label: 'Departments' },
    { key: 'classes', label: 'Classes and units' },
    { key: 'generate', label: 'Generate' },
    { key: 'publish', label: 'Review and publish' },
  ],
  exams: [
    { key: 'period', label: 'Exam period' },
    { key: 'papers', label: 'Papers' },
    { key: 'generate', label: 'Generate' },
    { key: 'publish', label: 'Review and publish' },
  ],
}

/** Old links (?tab=…) still land on the matching step. */
export const LEGACY_TABS: Record<string, { mode: Mode; step: number }> = {
  setup: { mode: 'teaching', step: 1 },
  departments: { mode: 'teaching', step: 2 },
  rows: { mode: 'teaching', step: 3 },
  units: { mode: 'teaching', step: 3 },
  runs: { mode: 'teaching', step: 4 },
  drafts: { mode: 'teaching', step: 5 },
  exams: { mode: 'exams', step: 0 },
}

export function useTeachingProgress(termId: string): { done: boolean[]; current: number } | null {
  const term = useTerm(termId)
  const status = useDepartmentStatus(termId)
  if (!term.data) return null
  const t = term.data
  // Smart Attendance unreachable: don't hold the Director on a step they can't finish.
  const departmentsDone = status.isError || (status.data ? status.data.published > 0 && status.data.needs_import === 0 : false)
  const done = [
    Boolean(t.start_date && t.end_date),
    departmentsDone,
    t.readiness.ready,
    t.drafts.length > 0,
    t.publications.length > 0,
  ]
  return { done, current: firstOpen(done) }
}

export function useExamProgress(termId: string): { done: boolean[]; current: number } | null {
  const exams = useExams(termId)
  if (!exams.data) return null
  const e = exams.data
  const done = [Boolean(e.period.exam_start && e.period.exam_end), e.papers.length > 0, e.drafts.length > 0, e.publications.length > 0]
  return { done, current: firstOpen(done) }
}

const firstOpen = (done: boolean[]) => {
  const i = done.indexOf(false)
  return i === -1 ? done.length : i + 1
}
