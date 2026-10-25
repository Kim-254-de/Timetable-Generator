import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get } from './api'
import type {
  BulkResult,
  ClassRow,
  Department,
  DepartmentList,
  DepartmentSync,
  DepartmentStatus,
  ExamDraftSummary,
  ExamGrid,
  ExamOverview,
  ExamPeriod,
  DraftSummary,
  Grid,
  Group,
  ImportResult,
  Me,
  Offering,
  PublicationItem,
  Room,
  RoomRecord,
  RoomType,
  Run,
  SmartttTerm,
  SnapshotSummary,
  Term,
  TermInput,
  TermOverview,
  View,
} from './types'

export const keys = {
  me: ['me'] as const,
  smartttTerms: ['smarttt-terms'] as const,
  terms: ['terms'] as const,
  term: (id: string) => ['term', id] as const,
  rows: (id: string) => ['rows', id] as const,
  offerings: (id: string) => ['offerings', id] as const,
  rooms: (id: string) => ['rooms', id] as const,
  runs: (id: string) => ['runs', id] as const,
  run: (id: string) => ['run', id] as const,
  grid: (id: string, view: View) => ['grid', id, view] as const,
  roomList: ['room-list'] as const,
  departments: ['departments'] as const,
  submissions: (id: string) => ['submissions', id] as const,
  exams: (id: string) => ['exams', id] as const,
  examDraft: (id: string) => ['exam-draft', id] as const,
}

const post = <T>(url: string, body?: unknown) => api.post<T>(url, body ?? {}).then((r) => r.data)
const patch = <T>(url: string, body: unknown) => api.patch<T>(url, body).then((r) => r.data)

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: () => get<Me>('/auth/me'), retry: false })
export const useSmartttTerms = () => useQuery({ queryKey: keys.smartttTerms, queryFn: () => get<SmartttTerm[]>('/smarttt/terms') })
export const useTerms = () => useQuery({ queryKey: keys.terms, queryFn: () => get<Term[]>('/terms') })
export const useTerm = (id: string) => useQuery({ queryKey: keys.term(id), queryFn: () => get<TermOverview>(`/terms/${id}`) })
export const useClassRows = (id: string) => useQuery({ queryKey: keys.rows(id), queryFn: () => get<ClassRow[]>(`/terms/${id}/class-rows`) })
export const useOfferings = (id: string) =>
  useQuery({ queryKey: keys.offerings(id), queryFn: () => get<Offering[]>(`/terms/${id}/offerings`) })
export const useRooms = (id: string) => useQuery({ queryKey: keys.rooms(id), queryFn: () => get<Room[]>(`/terms/${id}/rooms`) })

export const useRuns = (termId: string) =>
  useQuery({
    queryKey: keys.runs(termId),
    queryFn: () => get<Run[]>(`/terms/${termId}/runs`),
    // Poll while anything is still solving.
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === 'queued' || r.status === 'running') ? 3000 : false),
  })

export const useGrid = (draftId: string, view: View) =>
  useQuery({ queryKey: keys.grid(draftId, view), queryFn: () => get<Grid>(`/drafts/${draftId}`, { view }) })

export function useLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { identifier: string; password: string }) => post<Me>('/auth/login', body),
    onSuccess: (me) => qc.setQueryData(keys.me, me),
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/auth/logout'),
    onSettled: () => {
      qc.clear()
      qc.setQueryData(keys.me, null)
    },
  })
}

/** Any change to a term's setup invalidates everything derived from it. */
function useTermMutation<TVars, TData>(termId: string, fn: (vars: TVars) => Promise<TData>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      for (const k of [keys.term(termId), keys.rows(termId), keys.offerings(termId), keys.rooms(termId), keys.runs(termId), keys.departments]) {
        void qc.invalidateQueries({ queryKey: k })
      }
      void qc.invalidateQueries({ queryKey: ['grid'] })
    },
  })
}

export function useCreateTerm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TermInput) => post<Term>('/terms', body),
    onSettled: () => void qc.invalidateQueries({ queryKey: keys.terms }),
  })
}

export const usePatchTerm = (termId: string) =>
  useTermMutation(termId, (body: TermInput) => patch<Term>(`/terms/${termId}`, body))

export const useCopyTerm = (termId: string) =>
  useTermMutation(termId, (sourceTermId: string) =>
    post<{ class_rows_copied: number; units_copied: number }>(`/terms/${termId}/copy`, { source_term_id: sourceTermId }),
  )

// -- lecture halls and departments: shared by every term --------------------------------

/** Changing halls or departments changes every term's readiness and draft views. */
function useMasterMutation<TVars, TData>(key: readonly string[], fn: (vars: TVars) => Promise<TData>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: key })
      for (const k of ['term', 'rooms', 'offerings', 'rows', 'grid']) void qc.invalidateQueries({ queryKey: [k] })
    },
  })
}

export interface RoomInput {
  code?: string
  building?: string
  capacity?: number
  room_type?: RoomType
  active?: boolean
  unavailable?: number[]
  /** 0 or empty: capacity x the term's exam spacing. */
  exam_seats?: number | null
  for_exams?: boolean
}
export const useRoomList = () => useQuery({ queryKey: keys.roomList, queryFn: () => get<RoomRecord[]>('/rooms') })
export const useSaveRoom = () =>
  useMasterMutation(keys.roomList, ({ id, body }: { id?: string; body: RoomInput }) =>
    id ? patch<RoomRecord>(`/rooms/${id}`, body) : post<RoomRecord>('/rooms', body),
  )
export const useDeleteRoom = () => useMasterMutation(keys.roomList, (id: string) => api.delete(`/rooms/${id}`))
export const useBulkRooms = () =>
  useMasterMutation(keys.roomList, (rows: Record<string, string>[]) => post<BulkResult>('/rooms/bulk', { rows }))

/** The Generator's own fields; a department's name and school come from Smart Attendance. */
export interface DepartmentInput {
  code?: string
  lecturer_count?: number | null
}
const fetchDepartments = () => get<DepartmentList>('/departments')
/** Departments, read from Smart Attendance (at most once a minute) and kept here. */
export const useDepartmentList = () => useQuery({ queryKey: keys.departments, queryFn: fetchDepartments })
export const useDepartments = () =>
  useQuery({ queryKey: keys.departments, queryFn: fetchDepartments, select: (d) => d.departments })
export const useSaveDepartment = () =>
  useMasterMutation(keys.departments, ({ id, body }: { id: number; body: DepartmentInput }) =>
    patch<Department>(`/departments/${id}`, body),
  )
/** Reads the departments from Smart Attendance now. */
export const useSyncDepartments = () =>
  useMasterMutation(keys.departments, () => post<DepartmentSync>('/departments/sync'))
export const useDeleteDepartment = () =>
  useMasterMutation(keys.departments, (id: number) => api.delete(`/departments/${id}`))
export const useBulkDepartments = () =>
  useMasterMutation(keys.departments, (rows: Record<string, string>[]) => post<BulkResult>('/departments/bulk', { rows }))

// -- a term's class rows and units -----------------------------------------------------------

export interface ClassRowInput {
  program_code?: string
  study_year?: number
  study_semester?: number
  sub_class?: string
  /** A department's name or code, from the Departments list (Smart Attendance's). */
  department?: string
  student_count?: number | null
}
export const useCreateClassRow = (termId: string) =>
  useTermMutation(termId, (body: ClassRowInput) => post<ClassRow>(`/terms/${termId}/class-rows`, body))
/** What deleting a class row did: units only it took are deleted, shared units just lose the row. */
export interface ClassRowDeleted { units_deleted: string[]; units_kept: string[] }
export const useDeleteClassRow = (termId: string) =>
  useTermMutation(termId, async (id: string) => (await api.delete<ClassRowDeleted>(`/class-rows/${id}`)).data)
export const useBulkClassRows = (termId: string) =>
  useTermMutation(termId, (rows: Record<string, string>[]) => post<BulkResult>(`/terms/${termId}/class-rows/bulk`, { rows }))

export interface OfferingInput {
  unit_code?: string
  unit_name?: string
  /** A department's name or code, from the Departments list (Smart Attendance's). */
  department?: string
  weekly_hours?: number
  session_length?: number
  room_type?: RoomType
  class_row_ids?: string[]
}
export const useCreateOffering = (termId: string) =>
  useTermMutation(termId, (body: OfferingInput) => post<Offering>(`/terms/${termId}/offerings`, body))
export const useEditOffering = (termId: string) =>
  useTermMutation(termId, ({ id, body }: { id: string; body: OfferingInput }) => patch<Offering>(`/offerings/${id}`, body))
export const useDeleteOffering = (termId: string) =>
  useTermMutation(termId, (id: string) => api.delete(`/offerings/${id}`))
export const useBulkOfferings = (termId: string) =>
  useTermMutation(termId, (rows: Record<string, string>[]) => post<BulkResult>(`/terms/${termId}/offerings/bulk`, { rows }))

export function useOpenTerm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (smarttt_term_id: string) => post<Term>('/terms', { smarttt_term_id }),
    onSettled: () => void qc.invalidateQueries({ queryKey: keys.terms }),
  })
}

export const useSnapshot = (termId: string) =>
  useTermMutation(termId, () => post<SnapshotSummary>(`/terms/${termId}/snapshots`))
export const useImport = (termId: string) =>
  useTermMutation(termId, () =>
    post<{ class_rows_created: number; offerings_created: number; unresolved: string[] }>(`/terms/${termId}/setup/import`),
  )
export const usePatchRow = (termId: string) =>
  useTermMutation(termId, ({ id, body }: { id: string; body: ClassRowInput & { unavailable?: number[] } }) =>
    patch<ClassRow>(`/class-rows/${id}`, body),
  )
export const usePatchOffering = (termId: string) =>
  useTermMutation(
    termId,
    ({ id, body }: { id: string; body: Partial<Pick<Offering, 'weekly_hours' | 'session_length' | 'room_type'>> }) =>
      patch<Offering>(`/offerings/${id}`, body),
  )
export const useProposeGroups = (termId: string) =>
  useTermMutation(termId, (replace: boolean) =>
    post<{ proposed: number; skipped: { unit_code: string; reason: string }[] }>(`/terms/${termId}/groups/propose`, { replace }),
  )

export interface GroupInput {
  label: string
  members: { class_row_id: string; students: number }[]
}
export const useSaveGroup = (termId: string) =>
  useTermMutation(termId, ({ offeringId, groupId, body }: { offeringId: string; groupId?: string; body: GroupInput }) =>
    groupId ? patch<Group>(`/groups/${groupId}`, body) : post<Group>(`/offerings/${offeringId}/groups`, body),
  )
export const useDeleteGroup = (termId: string) =>
  useTermMutation(termId, (groupId: string) => api.delete(`/groups/${groupId}`))

export interface RunInput {
  mode: 'full' | 'repair'
  time_limit_s: number
  weights?: Record<string, number>
}
export const useStartRun = (termId: string) =>
  useTermMutation(termId, (body: RunInput) => post<Run>('/runs', { term_id: termId, ...body }))

export interface MoveInput {
  key: string
  day?: string
  start_time?: string
  room_id?: string
  pinned?: boolean
}
export function useMoveSession(draftId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, ...body }: MoveInput) => patch<DraftSummary>(`/drafts/${draftId}/sessions/${encodeURIComponent(key)}`, body),
    onSettled: () => void qc.invalidateQueries({ queryKey: ['grid', draftId] }),
  })
}

/** Re-solves around the pinned classes; `keep_published` also keeps every class of the published timetable. */
export const useResolve = (termId: string, draftId: string) =>
  useTermMutation(termId, ({ time_limit_s, keep_published }: { time_limit_s: number; keep_published: boolean }) =>
    post<Run>(`/drafts/${draftId}/resolve`, { time_limit_s, keep_published }))

// -- departments' teaching, from the Allocator ------------------------------------------------

export const useDepartmentStatus = (termId: string) =>
  useQuery({ queryKey: keys.submissions(termId), queryFn: () => get<DepartmentStatus>(`/terms/${termId}/departments`), retry: false })

export function useImportDepartments(termId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => post<ImportResult>(`/terms/${termId}/departments/import`),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.term(termId) })
      void qc.invalidateQueries({ queryKey: keys.rows(termId) })
      void qc.invalidateQueries({ queryKey: keys.offerings(termId) })
      void qc.invalidateQueries({ queryKey: keys.submissions(termId) })
      void qc.invalidateQueries({ queryKey: keys.departments })
    },
  })
}
export const useCopyDraft = (termId: string, draftId: string) =>
  useTermMutation(termId, () => post<DraftSummary>(`/drafts/${draftId}/copy`))
export const usePublish = (termId: string, draftId: string) =>
  useTermMutation(termId, (replace_unpublished: boolean) =>
    post<{ version: number; smarttt: { sent?: boolean; reason?: string; changes?: Record<string, unknown> } }>(`/drafts/${draftId}/publish`, {
      replace_unpublished,
    }),
  )

/** Sends an approved version SMARTTT missed (it was down), exactly as approved. */
export const useSendPublication = (termId: string) =>
  useTermMutation(termId, (version: number) => post<PublicationItem>(`/terms/${termId}/publications/${version}/send`, {}))

export type ExportFormat = 'pdf' | 'docx' | 'xlsx'
export const exportUrl = (draftId: string, view: View, format: ExportFormat = 'pdf') =>
  `${import.meta.env.VITE_API_URL ?? '/api'}/drafts/${draftId}/export.${format}?view=${view}`

// -- exams ----------------------------------------------------------------------------------

export const useExams = (termId: string) =>
  useQuery({ queryKey: keys.exams(termId), queryFn: () => get<ExamOverview>(`/terms/${termId}/exams`) })

export const useExamDepartments = (termId: string) =>
  useQuery({
    queryKey: ['exam-departments', termId],
    queryFn: () =>
      get<{ published: { code: string; name: string; published_at: string; papers: number }[]; not_published: { code: string; name: string }[] }>(
        `/terms/${termId}/exam-departments`,
      ),
    retry: false,
  })

function useExamMutation<TVars, TData>(termId: string, fn: (vars: TVars) => Promise<TData>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.exams(termId) })
      void qc.invalidateQueries({ queryKey: keys.runs(termId) })
      void qc.invalidateQueries({ queryKey: ['exam-draft'] })
      void qc.invalidateQueries({ queryKey: ['exam-departments', termId] })
      void qc.invalidateQueries({ queryKey: keys.rows(termId) })
    },
  })
}

export const usePatchExamPeriod = (termId: string) =>
  useExamMutation(termId, (body: Partial<Pick<ExamPeriod, 'exam_start' | 'exam_end' | 'exam_weekdays' | 'exam_days_off' | 'exam_sessions' | 'exam_spacing'>>) =>
    patch<ExamPeriod>(`/terms/${termId}/exam-period`, body))

export const useImportExams = (termId: string) =>
  useExamMutation(termId, () =>
    post<{ departments: string[]; papers: { added: string[]; changed: string[]; removed: string[] }; not_published: { code: string }[] }>(
      `/terms/${termId}/exams/import`,
    ))

export const useStartExamRun = (termId: string) =>
  useExamMutation(termId, (time_limit_s: number) => post<Run>('/exam-runs', { term_id: termId, time_limit_s }))

export const useExamDraft = (draftId: string) =>
  useQuery({ queryKey: keys.examDraft(draftId), queryFn: () => get<ExamGrid>(`/exam-drafts/${draftId}`) })

export const useMoveExamPaper = (termId: string, draftId: string) =>
  useExamMutation(termId, ({ paperId, day, session }: { paperId: string; day: string; session: number }) =>
    patch<ExamDraftSummary>(`/exam-drafts/${draftId}/papers/${paperId}`, { day, session, pinned: true }))

export const useExamDraftAction = (termId: string, draftId: string) =>
  useExamMutation(termId, (action: 'share' | 'copy' | 'publish' | 'resolve') =>
    post<ExamDraftSummary & { version?: number; id: string; draft_id?: string }>(`/exam-drafts/${draftId}/${action}`, action === 'resolve' ? { time_limit_s: 120 } : {}))

export const examExportUrl = (draftId: string, kind: 'timetable' | 'rooms' | 'roster', format: 'docx' | 'pdf') =>
  `${import.meta.env.VITE_API_URL ?? '/api'}/exam-drafts/${draftId}/export/${kind}.${format}`
