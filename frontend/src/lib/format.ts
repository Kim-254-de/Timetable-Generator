import type { Day } from './types'

export const DAYS: Day[] = ['MON', 'TUE', 'WED', 'THU', 'FRI']
export const DAY_NAMES: Record<Day, string> = { MON: 'Monday', TUE: 'Tuesday', WED: 'Wednesday', THU: 'Thursday', FRI: 'Friday' }
export const FIRST_HOUR = 7
export const HOURS = 12

export const slotOf = (day: Day, hour: number) => DAYS.indexOf(day) * HOURS + (hour - FIRST_HOUR)
export const slotDay = (slot: number) => DAYS[Math.floor(slot / HOURS)]
export const slotHour = (slot: number) => FIRST_HOUR + (slot % HOURS)
export const hh = (hour: number) => `${String(hour).padStart(2, '0')}:00`

export const termText = (t: { academic_year: string; semester: number }) => `${t.academic_year} · Semester ${t.semester}`

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString('en-KE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Nairobi' })

/** Soft-constraint scores, in the order and words the Director reads them. */
export const SCORE_LABELS: [string, string][] = [
  ['gaps', 'One-hour gaps'],
  ['same_day', 'Same unit twice in a day'],
  ['long_day', 'Hours beyond 5 a day'],
  ['early_starts', 'Starts at 07:00'],
  ['late_starts', 'Starts at 15:00 or later'],
  ['edge_hours', 'Hours at 07:00 or after 17:00'],
  ['building_changes', 'Extra buildings in a day'],
  ['empty_seats', 'Empty seats'],
  ['moved', 'Moved from published'],
]

export const RULES: Record<string, string> = {
  H1: 'Room double-booked',
  H2: 'Class row double-booked',
  H3: 'Room too small',
  H4: 'Wrong room type',
  H5: 'Not scheduled',
  H6: 'Outside teaching hours',
  H8: 'Unavailable hour',
  H9: 'Department over its lecturers',
  H10: 'Pinned session moved',
  H13: 'Allocated lecturer double-booked',
}
