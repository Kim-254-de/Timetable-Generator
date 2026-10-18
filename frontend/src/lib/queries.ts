import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get } from './api'
import type {
  ClassRow,
  DraftSummary,
  Grid,
  Group,
  Me,
  Offering,
  Room,
  Run,
  SmartttTerm,
  SnapshotSummary,
  Term,
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
      for (const k of [keys.term(termId), keys.rows(termId), keys.offerings(termId), keys.rooms(termId), keys.runs(termId)]) {
        void qc.invalidateQueries({ queryKey: k })
      }
      void qc.invalidateQueries({ queryKey: ['grid'] })
    },
  })
}

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
  useTermMutation(termId, ({ id, body }: { id: string; body: Partial<Pick<ClassRow, 'student_count' | 'unavailable'>> }) =>
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

export const useResolve = (termId: string, draftId: string) =>
  useTermMutation(termId, (time_limit_s: number) => post<Run>(`/drafts/${draftId}/resolve`, { time_limit_s }))
export const useCopyDraft = (termId: string, draftId: string) =>
  useTermMutation(termId, () => post<DraftSummary>(`/drafts/${draftId}/copy`))
export const usePublish = (termId: string, draftId: string) =>
  useTermMutation(termId, (replace_unpublished: boolean) =>
    post<{ version: number; smarttt: { changes?: Record<string, unknown> } }>(`/drafts/${draftId}/publish`, {
      replace_unpublished,
    }),
  )

export const exportUrl = (draftId: string, view: View) =>
  `${import.meta.env.VITE_API_URL ?? '/api'}/drafts/${draftId}/export.pdf?view=${view}`
