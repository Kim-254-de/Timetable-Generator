import { useState, type FormEvent } from 'react'
import { Check, KeyRound } from 'lucide-react'
import { Field, inputClass } from '@/components/Dialog'
import { Card, PageTitle, SidePanel, btn } from '@/components/ui'
import { errorMessage } from '@/lib/api'
import { useChangePassword, useMe, useRenameMe } from '@/lib/queries'

export const TITLES = ['Dr.', 'Prof.', 'Mr.', 'Ms.', 'Mrs.'] as const

/**
 * Smart Attendance keeps one full name. The profile shows it as title, first and last name:
 * a leading title is recognised, the last word is the last name and the rest the first.
 */
export function splitName(full: string): { title: string; first: string; last: string } {
  const words = full.split(/\s+/).filter(Boolean)
  const title = words.length > 1 && TITLES.some((t) => t.toLowerCase() === words[0].toLowerCase()) ? TITLES.find((t) => t.toLowerCase() === words[0].toLowerCase())! : ''
  const rest = title ? words.slice(1) : words
  if (rest.length <= 1) return { title, first: rest[0] ?? '', last: '' }
  return { title, first: rest.slice(0, -1).join(' '), last: rest[rest.length - 1] }
}

export const joinName = (p: { title: string; first: string; last: string }) =>
  [p.title, p.first.trim(), p.last.trim()].filter(Boolean).join(' ')

export function initialsOf(full: string): string {
  const { first, last } = splitName(full)
  return ((first[0] ?? '') + (last[0] ?? '')).toUpperCase() || '?'
}

export function ProfilePage() {
  const me = useMe()
  const rename = useRenameMe()
  const full = me.data?.full_name ?? ''
  const [name, setName] = useState(() => splitName(full))
  const [changing, setChanging] = useState(false)
  const next = joinName(name)
  const changed = next !== full

  const submit = (e: FormEvent) => {
    e.preventDefault()
    rename.mutate(next, { onSuccess: (m) => setName(splitName(m.full_name)) })
  }

  return (
    <div className="max-w-3xl space-y-5">
      <PageTitle title="My profile" crumb="Your account" />
      <section className="flex flex-wrap items-center gap-5 rounded-xl bg-brand-800 p-6 text-white sm:p-7">
        <span className="grid size-18 place-items-center rounded-2xl bg-gold-500 text-2xl font-bold text-on-gold">{initialsOf(full)}</span>
        <div>
          <p className="text-2xl font-bold">{full}</p>
          <p className="text-[15px] text-brand-100">Director, Examinations and Timetabling</p>
        </div>
      </section>

      <Card title="Your name">
        <form onSubmit={submit} className="space-y-4">
          <p className="text-sm text-muted">Shown here and in Smart Attendance, where your account is kept.</p>
          <div className="grid gap-4 sm:grid-cols-[8rem_1fr_1fr]">
            <Field label="Title">
              <select value={name.title} onChange={(e) => { rename.reset(); setName({ ...name, title: e.target.value }) }} className={inputClass}>
                <option value="">None</option>
                {TITLES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="First name">
              <input required autoComplete="given-name" value={name.first} maxLength={120}
                onChange={(e) => { rename.reset(); setName({ ...name, first: e.target.value }) }} className={inputClass} />
            </Field>
            <Field label="Last name">
              <input autoComplete="family-name" value={name.last} maxLength={120}
                onChange={(e) => { rename.reset(); setName({ ...name, last: e.target.value }) }} className={inputClass} />
            </Field>
          </div>
          {rename.isError && <p role="alert" className="text-sm text-danger">{errorMessage(rename.error)}</p>}
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" disabled={!changed || rename.isPending || !name.first.trim()} className={btn.primary}>
              {rename.isPending ? 'Saving…' : 'Save name'}
            </button>
            {rename.isSuccess && !changed && (
              <span role="status" className="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-3 py-1 text-xs font-semibold text-success">
                <Check className="size-3.5" aria-hidden /> Saved
              </span>
            )}
          </div>
        </form>
      </Card>

      <Card title="Sign-in">
        <dl className="grid gap-4 text-[15px] sm:grid-cols-2">
          <div><dt className="text-sm text-muted">Email</dt><dd className="mt-0.5 break-all">{me.data?.email || '—'}</dd></div>
          <div><dt className="text-sm text-muted">Account from</dt><dd className="mt-0.5">Smart Attendance invitation</dd></div>
        </dl>
        <p className="text-sm text-muted">To change your sign-in email, ask the Smart Attendance administrator.</p>
        <button type="button" onClick={() => setChanging(true)} className={btn.secondary}><KeyRound className="size-4" aria-hidden /> Change password</button>
      </Card>
      {changing && <PasswordPanel onClose={() => setChanging(false)} />}
    </div>
  )
}

function PasswordPanel({ onClose }: { onClose: () => void }) {
  const change = useChangePassword()
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const mismatch = form.confirm !== '' && form.next !== form.confirm
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (form.next !== form.confirm) return
    change.mutate({ current_password: form.current, new_password: form.next })
  }
  return (
    <SidePanel title="Change password" onClose={onClose}>
      {change.isSuccess ? (
        <div className="space-y-4">
          <p role="status" className="rounded-lg bg-success-soft px-4 py-3 text-sm text-success">
            Your password has been changed. You stay signed in here; anywhere else you were signed in to the Generator has been signed out.
          </p>
          <button type="button" onClick={onClose} className={btn.primary}>Done</button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <p className="text-sm text-muted">At least 6 characters, with a lowercase letter, an uppercase letter and a digit.</p>
          <Field label="Current password">
            <input type="password" required autoComplete="current-password" value={form.current}
              onChange={(e) => setForm({ ...form, current: e.target.value })} className={inputClass} />
          </Field>
          <Field label="New password">
            <input type="password" required minLength={6} maxLength={128} autoComplete="new-password" value={form.next}
              onChange={(e) => setForm({ ...form, next: e.target.value })} className={inputClass} />
          </Field>
          <Field label="New password again">
            <input type="password" required autoComplete="new-password" value={form.confirm} aria-invalid={mismatch}
              onChange={(e) => setForm({ ...form, confirm: e.target.value })} className={inputClass} />
          </Field>
          {mismatch && <p role="alert" className="text-sm text-danger">The two new passwords differ.</p>}
          {change.isError && <p role="alert" className="text-sm text-danger">{errorMessage(change.error)}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className={btn.secondary}>Cancel</button>
            <button type="submit" disabled={change.isPending || mismatch} className={btn.primary}>{change.isPending ? 'Changing…' : 'Change password'}</button>
          </div>
        </form>
      )}
    </SidePanel>
  )
}
