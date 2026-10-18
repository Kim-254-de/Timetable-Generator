import { useState, type FormEvent } from 'react'
import { Link, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AxiosError } from 'axios'
import { errorMessage } from '@/lib/api'
import { termText } from '@/lib/format'
import { useLogin, useLogout, useMe, useOpenTerm, useSmartttTerms, useTerms } from '@/lib/queries'
import { DraftPage } from '@/pages/DraftPage'
import { TermPage } from '@/pages/TermPage'

export function App() {
  const me = useMe()
  if (me.isPending) return <p className="p-8 text-sm text-slate-500">Loading…</p>
  const unauthenticated = me.isError && me.error instanceof AxiosError && me.error.response?.status === 401
  if (unauthenticated || me.data === null) return <LoginPage />
  if (me.isError) return <p role="alert" className="p-8 text-sm text-red-700">{errorMessage(me.error)}</p>

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<TermsPage />} />
        <Route path="terms/:termId" element={<TermPage />} />
        <Route path="terms/:termId/drafts/:draftId" element={<DraftPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

function Layout() {
  const me = useMe()
  const logout = useLogout()
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[110rem] items-center gap-4 px-4 py-3">
          <Link to="/" className="font-semibold text-emerald-800">Timetable Generator</Link>
          <span className="text-sm text-slate-500">Directorate of Examinations and Timetabling</span>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="text-slate-600">{me.data?.full_name}</span>
            <button onClick={() => logout.mutate()} className="text-emerald-700">Sign out</button>
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
      <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
        {terms.data?.map((t) => (
          <li key={t.id} className="px-4 py-3"><Link to={`/terms/${t.id}`} className="font-medium text-emerald-800">{termText(t)}</Link></li>
        ))}
        {terms.data?.length === 0 && <li className="px-4 py-3 text-sm text-slate-500">No term opened yet.</li>}
      </ul>
      <section className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-white p-4 text-sm">
        <label>Open a SMARTTT term
          <select value={choice} onChange={(e) => setChoice(e.target.value)} className="mt-1 block rounded-md border border-slate-300 px-2 py-1">
            <option value="">Choose…</option>
            {available.map((t) => <option key={t.id} value={t.id}>{termText(t)}{t.is_current ? ' (current)' : ''}</option>)}
          </select>
        </label>
        <button disabled={!choice || open.isPending} onClick={() => open.mutate(choice, { onSuccess: () => setChoice('') })}
          className="rounded-md bg-emerald-700 px-3 py-2 text-white disabled:opacity-50">Open</button>
        {(open.isError || smarttt.isError) && <p role="alert" className="w-full text-red-700">{errorMessage(open.error ?? smarttt.error)}</p>}
      </section>
    </div>
  )
}

function LoginPage() {
  const login = useLogin()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const submit = (e: FormEvent) => { e.preventDefault(); login.mutate({ identifier, password }) }
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Timetable Generator</h1>
          <p className="mt-1 text-sm text-slate-600">Directorate of Examinations and Timetabling. Sign in with your SMARTTT account.</p>
        </div>
        <label className="block text-sm"><span className="font-medium text-slate-700">Staff ID or email</span>
          <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" autoComplete="username" value={identifier}
            onChange={(e) => setIdentifier(e.target.value)} required />
        </label>
        <label className="block text-sm"><span className="font-medium text-slate-700">Password</span>
          <input type="password" className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" autoComplete="current-password"
            value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {login.isError && <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{errorMessage(login.error)}</p>}
        <button type="submit" disabled={login.isPending} className="w-full rounded-md bg-emerald-700 px-4 py-2 font-medium text-white disabled:opacity-60">
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
