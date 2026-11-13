import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import clsx from 'clsx'
import { X, type LucideIcon } from 'lucide-react'

/*
 * The building blocks every page uses, in SMARTTT's look (SMARTTT_fronted lib/core/theme/app_theme.dart):
 * royal blue fills, gold for the one big action, 16-20px rounded cards, bold buttons.
 * Screens stay short: a summary and one main action, with details in a SidePanel behind a button.
 */

export const btn = {
  primary: 'inline-flex items-center justify-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-strong disabled:opacity-50',
  gold: 'inline-flex items-center justify-center gap-2 rounded-2xl bg-gold-500 px-5 py-3 text-base font-bold text-on-gold hover:brightness-95 disabled:opacity-50',
  secondary: 'inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-card px-4 py-2.5 text-sm font-semibold text-brand-ink hover:bg-brand-soft disabled:opacity-50',
  quiet: 'inline-flex items-center justify-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium text-brand-ink hover:bg-brand-soft disabled:opacity-50',
  danger: 'inline-flex items-center justify-center gap-2 rounded-xl border border-danger/40 bg-card px-4 py-2.5 text-sm font-semibold text-danger hover:bg-danger-soft disabled:opacity-50',
}

export function Card({ children, className, title, action }: { children?: ReactNode; className?: string; title?: ReactNode; action?: ReactNode }) {
  return (
    <section className={clsx('space-y-4 rounded-xl border border-line bg-card p-5 sm:p-6', className)}>
      {(title || action) && (
        <div className="flex flex-wrap items-start justify-between gap-3">
          {title && <h2 className="text-lg font-semibold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

const TONES = {
  brand: 'bg-brand-soft text-brand-ink',
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
  teal: 'bg-teal-soft text-teal',
  violet: 'bg-violet-soft text-violet',
  muted: 'bg-surface text-muted',
}
export type Tone = keyof typeof TONES

export function IconBox({ icon: Icon, tone = 'brand', size = 'md' }: { icon: LucideIcon; tone?: Tone; size?: 'md' | 'lg' }) {
  return (
    <span className={clsx('grid shrink-0 place-items-center', TONES[tone], size === 'lg' ? 'size-12 rounded-2xl' : 'size-11 rounded-xl')}>
      <Icon className="size-5" aria-hidden />
    </span>
  )
}

export function Pill({ tone = 'brand', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={clsx('inline-flex items-center gap-1 whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold', TONES[tone])}>{children}</span>
}

export function StatCard({ icon, tone, value, label }: { icon: LucideIcon; tone: Tone; value: ReactNode; label: string }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-line bg-card p-5">
      <IconBox icon={icon} tone={tone} />
      <div>
        <p className="text-3xl font-bold tracking-tight">{value}</p>
        <p className="text-sm text-muted">{label}</p>
      </div>
    </div>
  )
}

/** A full-width bar with one message and, at most, one button. */
export function Notice({ tone = 'warning', icon: Icon, children, action }: { tone?: Tone; icon?: LucideIcon; children: ReactNode; action?: ReactNode }) {
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={clsx('flex flex-wrap items-center gap-3 rounded-lg px-4 py-3 text-sm', TONES[tone])}>
      {Icon && <Icon className="size-5 shrink-0" aria-hidden />}
      <div className="min-w-0 flex-1 basis-60">{children}</div>
      {action}
    </div>
  )
}

/**
 * Details live here instead of on the page: lists, forms and long explanations open from a button
 * and slide in from the right. Dialogs opened from inside it sit above it.
 */
export function SidePanel({ title, onClose, children, footer, wide = false }: {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    panel.current?.focus()
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previous }
  }, [])
  return (
    <div className="fixed inset-0 z-20" onKeyDown={(e) => { if (e.key === 'Escape' && !document.querySelector('[role=dialog][aria-modal=true]:not([data-panel])')) onClose() }}>
      <div className="absolute inset-0 bg-brand-950/40" onClick={onClose} aria-hidden />
      <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} data-panel
        className={clsx('absolute inset-y-0 right-0 flex w-full flex-col bg-card shadow-2xl outline-none', wide ? 'max-w-5xl' : 'max-w-lg')}>
        <div className="flex items-center gap-3 border-b border-line px-5 py-4 sm:px-6">
          <h2 className="min-w-0 flex-1 text-xl font-bold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="grid size-10 place-items-center rounded-xl border border-line text-muted hover:bg-surface">
            <X className="size-5" aria-hidden />
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5 sm:px-6">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-4 sm:px-6">{footer}</div>}
      </div>
    </div>
  )
}

/** A button that opens a SidePanel; the panel's content renders only while it is open. */
export function PanelButton({ label, title, className = btn.secondary, icon: Icon, wide, children }: {
  label: ReactNode
  title: string
  className?: string
  icon?: LucideIcon
  wide?: boolean
  children: ReactNode | ((close: () => void) => ReactNode)
}) {
  const [open, setOpen] = useState(false)
  const close = () => setOpen(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={className}>
        {Icon && <Icon className="size-4" aria-hidden />}{label}
      </button>
      {open && <SidePanel title={title} onClose={close} wide={wide}>{typeof children === 'function' ? children(close) : children}</SidePanel>}
    </>
  )
}

// -- the page title, shown in the top bar ------------------------------------------------

interface Heading { title: string; crumb?: string }
const HeadingContext = createContext<(h: Heading) => void>(() => {})
export const HeadingProvider = HeadingContext.Provider

/** Puts the page's title (and the small line above it) in the top bar. */
export function PageTitle({ title, crumb }: Heading) {
  const set = useContext(HeadingContext)
  useEffect(() => {
    set({ title, crumb })
    document.title = `${title} · Timetable Generator`
  }, [set, title, crumb])
  return null
}
