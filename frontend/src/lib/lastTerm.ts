/**
 * The term the Director last worked on, so the app opens straight on it.
 * Kept in this browser only; storage can be unavailable (private windows,
 * blocked site data), in which case the newest term is used.
 */
const KEY = 'generator.lastTermId'

export function readLastTerm(): string | null {
  try {
    return window.localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function rememberTerm(id: string): void {
  try {
    window.localStorage.setItem(KEY, id)
  } catch {
    // Not remembered; the app opens on the newest term instead.
  }
}
