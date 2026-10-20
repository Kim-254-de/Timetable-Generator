import type { ReactNode } from 'react'
import clsx from 'clsx'

export function Dialog({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div role="dialog" aria-modal="true" aria-label={title} className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 px-4"
      onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}>
      <div className={clsx('max-h-[90vh] w-full overflow-y-auto rounded-xl bg-card p-5 shadow-xl', wide ? 'max-w-4xl' : 'max-w-xl')}>
        <h2 className="text-lg font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-0.5 block text-xs text-muted">{hint}</span>}
    </label>
  )
}

export const inputClass = 'mt-1 w-full rounded-md border border-line px-2 py-1.5'
