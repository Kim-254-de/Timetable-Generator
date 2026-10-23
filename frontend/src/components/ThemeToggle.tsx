import { Laptop, Moon, Sun } from 'lucide-react'
import { useThemePreference, type ThemePreference } from '@/lib/theme'

// The icon shows what a tap switches to, not the current choice: System → Dark → Light → System.
const NEXT: Record<ThemePreference, ThemePreference> = { dark: 'light', light: 'system', system: 'dark' }
const ICON = { dark: Moon, light: Sun, system: Laptop }
const LABEL = { dark: 'Dark', light: 'Light', system: 'System' }

/** Top-bar button, left of the user's name. System follows the device; Dark and Light override it. */
export function ThemeToggle() {
  const [theme, setTheme] = useThemePreference()
  const next = NEXT[theme]
  const Icon = ICON[next]
  const label = `Switch to ${LABEL[next]} theme (now ${LABEL[theme]})`
  return (
    <button type="button" onClick={() => setTheme(next)} aria-label={label} title={label}
      className="grid size-8 place-items-center rounded-md text-brand-100 hover:bg-white/15 hover:text-white">
      <Icon className="size-4" aria-hidden />
    </button>
  )
}
