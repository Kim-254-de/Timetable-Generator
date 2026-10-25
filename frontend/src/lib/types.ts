export type Day = 'MON' | 'TUE' | 'WED' | 'THU' | 'FRI'
export type RoomType = 'lecture_hall' | 'lab' | 'seminar'
export type View = 'row' | 'room' | 'department'

export interface Me {
  account_id: string
  full_name: string
  university_id: string | null
  timetabling_office: boolean
}

export interface SmartttTerm {
  id: string
  academic_year: string
  semester: number
  is_current: boolean
}

export interface Term {
  id: string
  smarttt_term_id: string | null
  academic_year: string
  semester: number
  name: string
  start_date: string | null
  end_date: string | null
  version_label: string
  use_from: string | null
  prepared_by: string
  prepared_by_title: string
  default_session_length: number
}

export type TermInput = Partial<Omit<Term, 'id' | 'smarttt_term_id'>> & { copy_from_term_id?: string }

/** A lecture hall, lab or seminar room, shared by every term. */
export interface RoomRecord {
  id: string
  code: string
  building: string
  capacity: number
  room_type: RoomType
  active: boolean
  unavailable: number[]
  in_use: number
}

/**
 * A department, read from Smart Attendance (where an administrator creates
 * it with a name and a code). `lecturer_count` is the Generator's own; the
 * code is Attendance's when `code_from_attendance`, else made here.
 */
export interface Department {
  id: number
  code: string
  name: string
  /** True when the code is Attendance's: it can only be changed there. */
  code_from_attendance: boolean
  lecturer_count: number | null
  smarttt_department_id: number | null
  /** False for one entered here before departments came from Attendance. */
  from_attendance: boolean
  /** Active lecturers Attendance has placed in it: a guide for lecturer_count. */
  attendance_lecturer_count: number | null
}

export interface DepartmentList {
  attendance_connected: boolean
  departments: Department[]
}

export interface DepartmentSync extends DepartmentList {
  report: { linked: number; created: number; updated: number; skipped: string[] } | null
}

export interface BulkResult {
  created: number
  updated: number
  errors: { line: number; message: string }[]
  error_count: number
}

export interface Problem {
  code: string
  entity?: string
  message: string
}

export interface SnapshotSummary {
  id: string
  sha256: string
  taken_at: string
  taken_by: string
  counts: Record<string, number>
  source: 'local' | 'smarttt'
  published_version: number | null
  published_sessions: number
  warnings: { code: string; detail: string }[]
}

export interface Readiness {
  ready: boolean
  problems: Problem[]
  problem_count?: number
  snapshot?: SnapshotSummary
}

export interface DraftListItem {
  id: string
  name: string
  status: 'draft' | 'published' | 'superseded'
  created_at: string
  soft_scores: Record<string, number>
  session_count: number
}

export interface PublicationItem {
  version: number
  draft_id: string
  published_by: string
  published_at: string
  changes: { added?: string[]; moved?: string[]; removed?: string[]; unchanged?: number } | null
  sent_to_smarttt: boolean
  not_sent_reason: string | null
  /** Not yet in SMARTTT, the latest version, and SMARTTT has the term: it can be sent now. */
  can_send: boolean
}

export interface TermOverview extends Term {
  readiness: Readiness
  drafts: DraftListItem[]
  publications: PublicationItem[]
}

export interface ClassRow {
  id: string
  label: string
  program_id: number | null
  program_code: string
  department_id: number | null
  study_year: number
  study_semester: number
  sub_class: string
  student_count: number | null
  unavailable: number[]
  /** Entered by its department in Smart Attendance, and edited only there (but its unavailable hours). */
  from_allocator: boolean
}

export interface GroupMember {
  class_row_id: string
  label: string | null
  students: number
}

export interface Group {
  id: string
  label: string
  student_count: number
  members: GroupMember[]
  lecturer_staff_number?: string | null
  lecturer_name?: string
}

export interface Offering {
  id: string
  unit_id: number | null
  unit_code: string
  unit_name: string
  department_id: number
  weekly_hours: number | null
  session_length: number | null
  room_type: RoomType
  source: string
  /** Entered by its department in Smart Attendance, and edited only there. */
  from_allocator: boolean
  class_row_ids: string[]
  class_rows: string[]
  groups: Group[]
}

/** A department's teaching in Smart Attendance: published or not yet, and whether it is imported. */
export interface DepartmentSubmission {
  code: string
  name: string
  published: boolean
  published_at?: string
  published_by?: string | null
  units?: number
  reopened_at?: string | null
  last_published_at?: string | null
  changed_units?: string[]
  imported_at: string | null
  needs_import: boolean
}

export interface DepartmentStatus {
  departments: DepartmentSubmission[]
  published: number
  not_published: number
  needs_import: number
}

export interface ImportChanges { added: string[]; changed: string[]; removed: string[] }

export interface ImportResult {
  departments: string[]
  class_rows: ImportChanges
  units: Record<string, ImportChanges>
  not_published: { code: string; name: string }[]
}

export interface Reason {
  rule: string
  entity?: string
  message: string
}

export interface Run {
  id: string
  term_id: string
  mode: 'full' | 'resolve' | 'repair'
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  base_draft_id: string | null
  weights: Record<string, number>
  time_limit_s: number
  progress: { phase?: string; objective?: number; seconds?: number; status?: string; sessions?: number }
  score: number | null
  soft_scores: Record<string, number>
  solve_seconds: number | null
  failure: { stage: string; count: number; reasons: Reason[] } | null
  draft_id: string | null
  created_by: string
  created_at: string
  finished_at: string | null
}

export interface Violation {
  rule: string
  message: string
  session_keys: string[]
}

export interface DraftSummary {
  id: string
  term_id: string
  name: string
  status: 'draft' | 'published' | 'superseded'
  session_count: number
  pinned: number
  soft_scores: Record<string, number>
  violations: Violation[]
  violation_count: number
  stale: { missing: string[]; extra: string[] }
  publishable: boolean
}

export interface Cell {
  key: string
  unit_code: string
  group: string
  lecturer?: string
  room_id: string
  room: string
  day: Day
  start_time: string
  end_time: string
  start_slot: number
  length: number
  pinned: boolean
  students: number | null
}

export interface Entity {
  id: string
  label: string
  cells: Cell[]
  capacity?: number
  building?: string
}

export interface Grid {
  draft: DraftSummary
  view: View
  days: Day[]
  first_hour: number
  hours: number
  /** An approved version, shown exactly as it was approved. */
  as_approved: boolean
  entities: Entity[]
}

export interface Room {
  id: string
  code: string
  name: string
  building: string
  capacity: number
  capacity_confirmed: boolean
  room_type: RoomType
}

export interface ApiErrorBody {
  message: string
  code?: string
  details?: unknown
}
