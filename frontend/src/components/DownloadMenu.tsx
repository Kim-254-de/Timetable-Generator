import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ChevronDown, Download } from 'lucide-react'
import { btn } from './ui'

export type MenuItem = { label: string; href: string } | { label: string; onClick: () => void; busy?: boolean }

/** One "Download" button in place of a row of links: the formats open in a small menu. */
export function DownloadMenu({ items, label = 'Download', note }: { items: MenuItem[]; label?: string; note?: ReactNode }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [open])
  const item = 'block w-full rounded-lg px-3 py-2 text-left text-sm text-ink hover:bg-brand-soft disabled:opacity-60'
  return (
    <div ref={box} className="relative" onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false) }}>
      <button type="button" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen(!open)} className={btn.secondary}>
        <Download className="size-4" aria-hidden /> {label} <ChevronDown className="size-4" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-10 mt-2 min-w-56 space-y-0.5 rounded-xl border border-line bg-card p-2 shadow-xl">
          {items.map((it) => 'href' in it
            ? <a key={it.label} role="menuitem" href={it.href} className={item} onClick={() => setOpen(false)}>{it.label}</a>
            : <button key={it.label} role="menuitem" type="button" disabled={it.busy} className={item} onClick={() => { it.onClick(); setOpen(false) }}>{it.label}</button>)}
          {note && <p className="px-3 pb-1 pt-2 text-xs text-muted">{note}</p>}
        </div>
      )}
    </div>
  )
}
