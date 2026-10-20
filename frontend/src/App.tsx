import { useState, type FormEvent } from 'react'
import { Link, Navigate, NavLink, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { AxiosError } from 'axios'
import clsx from 'clsx'
import { Field, inputClass } from '@/components/Dialog'
import { errorMessage } from '@/lib/api'
import { termText } from '@/lib/format'
import { readLastTerm } from '@/lib/lastTerm'
import { useCreateTerm, useLogin, useLogout, useMe, useOpenTerm, useSmartttTerms, useTerms } from '@/lib/queries'
import { DepartmentsPage } from '@/pages/DepartmentsPage'
import { DraftPage } from '@/pages/DraftPage'
import { RoomsPage } from '@/pages/RoomsPage'
import { TermPage } from '@/pages/TermPage'

export function App() {
  const me = useMe()
  if (me.isPending) return <p className="p-8 text-sm text-muted">Loading…</p>
  const unauthenticated = me.isError && me.error instanceof AxiosError && me.error.response?.status === 401
  if (unauthenticated || me.data === null) return <LoginPage />
  if (me.isError) return <p role="alert" className="p-8 text-sm text-danger">{errorMessage(me.error)}</p>

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="terms" element={<TermsPage />} />
        <Route path="rooms" element={<RoomsPage />} />
        <Route path="departments" element={<DepartmentsPage />} />
        <Route path="terms/:termId" element={<TermPage />} />
        <Route path="terms/:termId/drafts/:draftId" element={<DraftPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

/** Home is the term being worked on: the one last opened here, else the newest. */
function HomePage() {
  const terms = useTerms()
  if (terms.isPending) return <p className="text-sm text-muted">Loading…</p>
  if (terms.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(terms.error)}</p>
  const last = readLastTerm()
  const term = terms.data.find((t) => t.id === last) ?? terms.data[0]
  return term ? <Navigate to={`/terms/${term.id}`} replace /> : <TermsPage />
}

const NAV = [['/', 'Home'], ['/terms', 'Terms'], ['/rooms', 'Lecture halls'], ['/departments', 'Departments']] as const

function Layout() {
  const me = useMe()
  const logout = useLogout()
  const { pathname } = useLocation()
  const onTerm = pathname.startsWith('/terms/')
  return (
    <div className="min-h-screen bg-surface text-ink">
      <header className="border-b-2 border-gold-500 bg-topbar text-white">
        <div className="mx-auto flex max-w-[110rem] items-center gap-4 px-4 py-3">
          <Link to="/" className="font-semibold">Timetable Generator</Link>
          <nav className="flex gap-1 text-sm">
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} end
                className={({ isActive }) => clsx('rounded-md px-2 py-1', isActive || (to === '/' && onTerm) ? 'bg-white/15 text-white' : 'text-brand-100 hover:text-white')}>
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="text-brand-100">{me.data?.full_name}</span>
            <button onClick={() => logout.mutate()} className="font-medium text-gold-500 hover:underline">Sign out</button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[110rem] px-4 py-6"><Outlet /></main>
    </div>
  )
}

function TermsPage() {
  const terms = useTerms()
  const smarttt = useSmartttTerms()
  const open = useOpenTerm()
  const [choice, setChoice] = useState('')
  const opened = new Set(terms.data?.map((t) => t.smarttt_term_id))
  const available = (smarttt.data ?? []).filter((t) => !opened.has(t.id))

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-xl font-semibold">Terms</h1>
      <ul className="divide-y divide-line rounded-lg border border-line bg-card">
        {terms.data?.map((t) => (
          <li key={t.id} className="px-4 py-3">
            <Link to={`/terms/${t.id}`} className="font-medium text-brand-ink">{t.name || termText(t)}</Link>
            {t.name && <span className="ml-2 text-sm text-muted">{termText(t)}</span>}
          </li>
        ))}
        {terms.data?.length === 0 && <li className="px-4 py-3 text-sm text-muted">No term yet. Create the first one below.</li>}
      </ul>
      <CreateTermForm />
      {/* Opening a SMARTTT term is optional; it only shows when SMARTTT is connected. */}
      {smarttt.isSuccess && available.length > 0 && (
        <section className="flex flex-wrap items-end gap-2 rounded-lg border border-line bg-card p-4 text-sm">
          <label>Or open a term from SMARTTT
            <select value={choice} onChange={(e) => setChoice(e.target.value)} className="mt-1 block rounded-md border border-line px-2 py-1">
              <option value="">Choose…</option>
              {available.map((t) => <option key={t.id} value={t.id}>{termText(t)}{t.is_current ? ' (current)' : ''}</option>)}
            </select>
          </label>
          <button disabled={!choice || open.isPending} onClick={() => open.mutate(choice, { onSuccess: () => setChoice('') })}
            className="rounded-md border border-line px-3 py-2 disabled:opacity-50">Open</button>
          {open.isError && <p role="alert" className="w-full text-danger">{errorMessage(open.error)}</p>}
        </section>
      )}
    </div>
  )
}

function CreateTermForm() {
  const terms = useTerms()
  const create = useCreateTerm()
  const navigate = useNavigate()
  const [form, setForm] = useState({ academic_year: '', semester: 1, name: '', start_date: '', end_date: '', copy_from_term_id: '' })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate(
      {
        academic_year: form.academic_year.trim(),
        semester: form.semester,
        name: form.name.trim() || undefined,
        start_date: form.start_date || undefined,
        end_date: form.end_date || undefined,
        copy_from_term_id: form.copy_from_term_id || undefined,
      },
      { onSuccess: (t) => navigate(`/terms/${t.id}`) },
    )
  }
  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-card p-4">
      <h2 className="font-semibold">Create a new term</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Academic year" hint="e.g. 2026/2027">
          <input required pattern="\d{4}/\d{4}" value={form.academic_year} onChange={(e) => setForm({ ...form, academic_year: e.target.value })}
            placeholder="2026/2027" className={inputClass} />
        </Field>
        <Field label="Semester" hint="May–August is semester 3">
          <select value={form.semester} onChange={(e) => setForm({ ...form, semester: Number(e.target.value) })} className={inputClass}>
            <option value={1}>1</option><option value={2}>2</option><option value={3}>3</option>
          </select>
        </Field>
        <Field label="Name on the timetable" hint="e.g. September-December 2026">
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputClass} />
        </Field>
        <Field label="Start date"><input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className={inputClass} /></Field>
        <Field label="End date"><input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} className={inputClass} /></Field>
        <Field label="Copy class rows and units from" hint="Optional: start from a previous term">
          <select value={form.copy_from_term_id} onChange={(e) => setForm({ ...form, copy_from_term_id: e.target.value })} className={inputClass}>
            <option value="">Start empty</option>
            {terms.data?.map((t) => <option key={t.id} value={t.id}>{t.name || termText(t)}</option>)}
          </select>
        </Field>
      </div>
      {create.isError && <p role="alert" className="text-sm text-danger">{errorMessage(create.error)}</p>}
      <button type="submit" disabled={create.isPending} className="rounded-md bg-brand px-4 py-2 text-sm text-white disabled:opacity-50">
        {create.isPending ? 'Creating…' : 'Create term'}
      </button>
    </form>
  )
}

function LoginPage() {
  const login = useLogin()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const submit = (e: FormEvent) => { e.preventDefault(); login.mutate({ identifier, password }) }
  return (
    <main className="flex min-h-screen items-center justify-center bg-surface px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-line bg-card p-8 shadow-sm">
        <div>
          <h1 className="text-xl font-semibold text-ink">Timetable Generator</h1>
          <p className="mt-1 text-sm text-muted">Directorate of Examinations and Timetabling. Sign in with your university (SMARTTT) account.</p>
        </div>
        <label className="block text-sm"><span className="font-medium text-ink">Staff ID or email</span>
          <input className="mt-1 w-full rounded-md border border-line px-3 py-2" autoComplete="username" value={identifier}
            onChange={(e) => setIdentifier(e.target.value)} required />
        </label>
        <label className="block text-sm"><span className="font-medium text-ink">Password</span>
          <input type="password" className="mt-1 w-full rounded-md border border-line px-3 py-2" autoComplete="current-password"
            value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {login.isError && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{errorMessage(login.error)}</p>}
        <button type="submit" disabled={login.isPending} className="w-full rounded-md bg-brand px-4 py-2 font-medium text-white disabled:opacity-60">
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
