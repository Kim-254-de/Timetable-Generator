import { useSyncExternalStore } from 'react'

export type ThemePreference = 'system' | 'light' | 'dark'

// index.html reads the same key before first paint; keep the two in step.
const STORAGE_KEY = 'theme'
const darkQuery = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null
const listeners = new Set<() => void>()

function read(): ThemePreference {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system' // storage blocked: follow the device
  }
}

let current = read()

function apply() {
  const dark = current === 'dark' || (current === 'system' && !!darkQuery?.matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}

// Imported from main.tsx so System tracks the device on every page, not only where the switcher is.
darkQuery?.addEventListener('change', () => { if (current === 'system') apply() })

export function setThemePreference(next: ThemePreference) {
  current = next
  try {
    if (next === 'system') localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, next)
  } catch {
    // not saved; the choice still holds until the page reloads
  }
  apply()
  listeners.forEach((l) => l())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function useThemePreference(): [ThemePreference, (next: ThemePreference) => void] {
  const value = useSyncExternalStore(subscribe, () => current, () => 'system' as const)
  return [value, setThemePreference]
}
