import { useCallback, useState, type FormEvent } from 'react'
import { Link, Navigate, NavLink, Outlet, Route, Routes, useNavigate } from 'react-router-dom'
import { AxiosError } from 'axios'
import clsx from 'clsx'
import {
  AlertTriangle, ArrowRight, BookOpen, Building2, CalendarDays, CalendarRange, ChevronRight, Download, FileText, House,
  Layers, LogOut, PenLine, Play, Plus, Users,
} from 'lucide-react'
import { Field, inputClass } from '@/components/Dialog'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Card, HeadingProvider, IconBox, Notice, PageTitle, Pill, SidePanel, StatCard, btn } from '@/components/ui'
import { errorMessage } from '@/lib/api'
import { termText } from '@/lib/format'
import { readLastTerm } from '@/lib/lastTerm'
import { STEPS, useTeachingProgress } from '@/lib/steps'
import {
  useClassRows, useCreateTerm, useDepartmentStatus, useLogin, useLogout, useMe, useOfferings, useOpenTerm, useRoomList,
  useSmartttTerms, useTerm, useTerms,
} from '@/lib/queries'
import type { Term } from '@/lib/types'
import { DepartmentsPage } from '@/pages/DepartmentsPage'
import { DraftPage } from '@/pages/DraftPage'
import { ExamDraftPage } from '@/pages/ExamDraftPage'
import { ProfilePage, initialsOf } from '@/pages/ProfilePage'
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
        <Route path="profile" element={<ProfilePage />} />
        <Route path="terms/:termId" element={<TermPage />} />
        <Route path="terms/:termId/drafts/:draftId" element={<DraftPage />} />
        <Route path="terms/:termId/exam-drafts/:draftId" element={<ExamDraftPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

/** The term being worked on: the one last opened here, else the newest. */
function useWorkingTerm(): Term | undefined {
  const terms = useTerms()
  const last = readLastTerm()
  return terms.data?.find((t) => t.id === last) ?? terms.data?.[0]
}

const NAV = [
  { to: '/', label: 'Home', icon: House, end: true },
  { to: '/terms', label: 'Terms', icon: CalendarDays, end: false },
  { to: '/rooms', label: 'Lecture halls', icon: Building2, end: true },
  { to: '/departments', label: 'Departments', icon: Users, end: true },
] as const

function Layout() {
  const me = useMe()
  const logout = useLogout()
  const working = useWorkingTerm()
  const [heading, setHeading] = useState<{ title: string; crumb?: string }>({ title: '' })
  const set = useCallback((h: { title: string; crumb?: string }) => setHeading(h), [])

  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink md:flex-row">
      {/* SMARTTT's royal blue sidebar; across the top on a phone. */}
      <aside className="flex shrink-0 flex-col gap-6 bg-sidebar px-4 py-4 text-white md:sticky md:top-0 md:h-screen md:w-64 md:py-6">
        <Link to="/" className="flex items-center gap-3 px-2">
          <span className="grid size-10 place-items-center rounded-xl bg-gold-500 text-on-gold"><CalendarRange className="size-5" aria-hidden /></span>
          <span className="leading-tight"><span className="block text-lg font-bold">Timetable</span><span className="block text-sm text-brand-100">Generator</span></span>
        </Link>
        <nav aria-label="Main" className="-mx-1 flex gap-1 overflow-x-auto px-1 md:flex-col md:overflow-visible">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => clsx('flex shrink-0 items-center gap-3 rounded-xl px-3.5 py-2.5 text-[15px] font-medium',
                isActive ? 'bg-white font-semibold text-brand-800' : 'text-brand-100 hover:bg-white/10 hover:text-white')}>
              <Icon className="size-5" aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>
        {working && (
          <div className="mt-auto hidden space-y-3 rounded-2xl bg-white/10 p-4 md:block">
            <p className="text-xs uppercase tracking-wider text-brand-100">Working on</p>
            <p className="font-semibold">{working.name || termText(working)}</p>
            <Link to={`/terms/${working.id}`} className="flex h-10 items-center justify-center rounded-xl bg-gold-500 text-sm font-semibold text-on-gold hover:brightness-95">Open term</Link>
          </div>
        )}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-4 border-b-[3px] border-gold-500 bg-card px-4 py-4 sm:px-8">
          <div className="min-w-0 flex-1">
            {heading.crumb && <p className="truncate text-sm text-muted">{heading.crumb}</p>}
            <h1 className="truncate text-2xl font-bold tracking-tight">{heading.title}</h1>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link to="/profile" aria-label="My profile" className="flex items-center gap-2.5 rounded-xl border border-line py-1 pl-1 pr-3 hover:bg-surface">
              <span className="grid size-9 place-items-center rounded-lg bg-brand-soft text-sm font-bold text-brand-ink">{initialsOf(me.data?.full_name ?? '')}</span>
              <span className="hidden leading-tight sm:block">
                <span className="block text-sm font-semibold">{me.data?.full_name}</span>
                <span className="block text-xs text-muted">Director</span>
              </span>
            </Link>
            <button type="button" onClick={() => logout.mutate()} aria-label="Sign out" title="Sign out"
              className="grid size-11 place-items-center rounded-xl border border-line text-muted hover:bg-surface">
              <LogOut className="size-5" aria-hidden />
            </button>
          </div>
        </header>
        <main className="w-full max-w-[110rem] flex-1 px-4 py-6 sm:px-8 sm:py-8">
          <HeadingProvider value={set}><Outlet /></HeadingProvider>
        </main>
      </div>
    </div>
  )
}

// -- Home ---------------------------------------------------------------------------------

function HomePage() {
  const terms = useTerms()
  const term = useWorkingTerm()
  if (terms.isPending) return <p className="text-sm text-muted">Loading…</p>
  if (terms.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(terms.error)}</p>
  if (!term) return <TermsPage />
  return <HomeDashboard termId={term.id} />
}

const greeting = () => {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

function HomeDashboard({ termId }: { termId: string }) {
  const me = useMe()
  const term = useTerm(termId)
  const progress = useTeachingProgress(termId)
  const status = useDepartmentStatus(termId)
  const rows = useClassRows(termId)
  const offerings = useOfferings(termId)
  const rooms = useRoomList()
  const t = term.data
  const latest = t?.drafts[0]
  const steps = STEPS.teaching
  const current = progress?.current ?? 1
  const allDone = progress ? progress.done.every(Boolean) : false
  const firstName = (me.data?.full_name ?? '').split(' ').find((w) => w.length > 1 && !w.endsWith('.')) ?? ''

  const quick = [
    { to: `/terms/${termId}?step=2`, icon: Download, label: "Departments' teaching", hint: 'Import what they published' },
    { to: `/terms/${termId}?step=4`, icon: Play, label: 'Generate', hint: 'Make a new draft' },
    latest
      ? { to: `/terms/${termId}/drafts/${latest.id}`, icon: FileText, label: 'Latest draft', hint: latest.name }
      : { to: `/terms/${termId}?step=5`, icon: FileText, label: 'Timetables', hint: 'Drafts and downloads' },
    { to: `/terms/${termId}?mode=exams`, icon: PenLine, label: 'Exam timetable', hint: 'Period, papers, rooms' },
  ]

  return (
    <div className="space-y-6">
      <PageTitle title="Home" crumb="Directorate of Examinations and Timetabling" />
      <section className="flex flex-wrap items-center gap-6 rounded-xl bg-brand-800 p-6 text-white sm:p-7">
        <div className="min-w-0 flex-1 basis-72 space-y-2">
          <p className="text-sm text-brand-100">{greeting()}{firstName ? `, ${firstName}` : ''}</p>
          <h2 className="text-2xl font-bold">{t ? t.name || termText(t) : '…'}</h2>
          <p className="text-[15px] text-brand-100">
            {allDone ? 'Teaching timetable published.' : `Teaching timetable: step ${current} of ${steps.length}, ${steps[current - 1].label.toLowerCase()}`}
          </p>
          <div className="flex gap-1.5 pt-2" aria-hidden>
            {steps.map((s, i) => (
              <span key={s.key} className={clsx('h-1.5 w-12 rounded-full', progress?.done[i] ? 'bg-gold-500' : i + 1 === current ? 'bg-white' : 'bg-white/25')} />
            ))}
          </div>
        </div>
        <Link to={`/terms/${termId}`} className={btn.gold}>Continue <ArrowRight className="size-5" aria-hidden /></Link>
      </section>

      <section aria-label="At a glance" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Users} tone="brand" label="Departments published"
          value={status.data ? `${status.data.published}/${status.data.departments.length}` : '–'} />
        <StatCard icon={Layers} tone="success" label="Class rows" value={rows.data?.length ?? '–'} />
        <StatCard icon={BookOpen} tone="warning" label="Units" value={offerings.data?.length ?? '–'} />
        <StatCard icon={Building2} tone="violet" label="Lecture halls" value={rooms.data?.length ?? '–'} />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Quick actions</h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {quick.map((q) => (
            <Link key={q.label} to={q.to} className="flex items-center gap-4 rounded-xl border border-line bg-card p-4 hover:border-brand-200 hover:bg-brand-soft/40">
              <IconBox icon={q.icon} size="lg" />
              <span className="min-w-0">
                <span className="block font-semibold">{q.label}</span>
                <span className="block truncate text-sm text-muted">{q.hint}</span>
              </span>
            </Link>
          ))}
        </div>
      </section>

      {status.data && status.data.not_published > 0 && (
        <Notice icon={AlertTriangle} action={<Link to={`/terms/${termId}?step=2`} className={btn.secondary}>See who</Link>}>
          {status.data.not_published === 1 ? '1 department has' : `${status.data.not_published} departments have`} not published their teaching yet.
        </Notice>
      )}
      {t && !t.readiness.ready && progress && progress.current >= 3 && (
        <Notice icon={AlertTriangle} action={<Link to={`/terms/${termId}?step=3`} className={btn.secondary}>Fix them</Link>}>
          {t.readiness.problem_count ?? t.readiness.problems.length} things to fix before generating.
        </Notice>
      )}
    </div>
  )
}

// -- Terms --------------------------------------------------------------------------------

function TermsPage() {
  const terms = useTerms()
  const smarttt = useSmartttTerms()
  const open = useOpenTerm()
  const [creating, setCreating] = useState(false)
  const [choice, setChoice] = useState('')
  const working = useWorkingTerm()
  const opened = new Set(terms.data?.map((t) => t.smarttt_term_id))
  const available = (smarttt.data ?? []).filter((t) => !opened.has(t.id))

  return (
    <div className="max-w-4xl space-y-4">
      <PageTitle title="Terms" crumb="All terms" />
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-0 flex-1 basis-60 text-[15px] text-muted">Pick a term to work on, or start a new one.</p>
        <button type="button" onClick={() => setCreating(true)} className={btn.primary}><Plus className="size-4" aria-hidden /> New term</button>
      </div>
      {terms.isError && <p role="alert" className="text-sm text-danger">{errorMessage(terms.error)}</p>}
      {terms.data?.map((t) => (
        <Link key={t.id} to={`/terms/${t.id}`} className="flex flex-wrap items-center gap-4 rounded-xl border border-line bg-card px-5 py-4 hover:border-brand-200">
          <IconBox icon={CalendarDays} size="lg" />
          <span className="min-w-0 flex-1 basis-56">
            <span className="block text-[17px] font-semibold">{t.name || termText(t)}</span>
            <span className="block text-sm text-muted">{termText(t)}{t.smarttt_term_id ? ' · in SMARTTT' : ''}</span>
          </span>
          {t.id === working?.id && <Pill tone="success">Working on</Pill>}
          <ChevronRight className="size-5 text-muted" aria-hidden />
        </Link>
      ))}
      {terms.data?.length === 0 && (
        <Card><p className="text-sm text-muted">No term yet. Start the first one with New term.</p></Card>
      )}
      {/* Opening a SMARTTT term is optional; it only shows when SMARTTT is connected. */}
      {smarttt.isSuccess && available.length > 0 && (
        <Card title="Or open a term from SMARTTT">
          <div className="flex flex-wrap items-end gap-2 text-sm">
            <select aria-label="SMARTTT term" value={choice} onChange={(e) => setChoice(e.target.value)} className={clsx(inputClass, 'mt-0 w-auto')}>
              <option value="">Choose…</option>
              {available.map((t) => <option key={t.id} value={t.id}>{termText(t)}{t.is_current ? ' (current)' : ''}</option>)}
            </select>
            <button type="button" disabled={!choice || open.isPending} onClick={() => open.mutate(choice, { onSuccess: () => setChoice('') })} className={btn.secondary}>Open</button>
          </div>
          {open.isError && <p role="alert" className="text-sm text-danger">{errorMessage(open.error)}</p>}
        </Card>
      )}
      {creating && <CreateTermPanel onClose={() => setCreating(false)} />}
    </div>
  )
}

function CreateTermPanel({ onClose }: { onClose: () => void }) {
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
    <SidePanel title="New term" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
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
        <div className="grid grid-cols-2 gap-3">
          <Field label="Start date"><input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className={inputClass} /></Field>
          <Field label="End date"><input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} className={inputClass} /></Field>
        </div>
        <Field label="Copy class rows and units from" hint="Optional: start from a previous term">
          <select value={form.copy_from_term_id} onChange={(e) => setForm({ ...form, copy_from_term_id: e.target.value })} className={inputClass}>
            <option value="">Start empty</option>
            {terms.data?.map((t) => <option key={t.id} value={t.id}>{t.name || termText(t)}</option>)}
          </select>
        </Field>
        {create.isError && <p role="alert" className="text-sm text-danger">{errorMessage(create.error)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className={btn.secondary}>Cancel</button>
          <button type="submit" disabled={create.isPending} className={btn.primary}>{create.isPending ? 'Creating…' : 'Create term'}</button>
        </div>
      </form>
    </SidePanel>
  )
}

// -- Sign-in ------------------------------------------------------------------------------

function LoginPage() {
  const login = useLogin()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const submit = (e: FormEvent) => { e.preventDefault(); login.mutate({ identifier, password }) }
  return (
    <main className="flex min-h-screen items-center justify-center bg-surface px-4">
      <form onSubmit={submit} className="w-full max-w-md overflow-hidden rounded-xl border border-line bg-card shadow-sm">
        <div className="flex items-center gap-3 border-b-[3px] border-gold-500 bg-brand-800 px-8 py-6 text-white">
          <span className="grid size-11 place-items-center rounded-xl bg-gold-500 text-on-gold"><CalendarRange className="size-6" aria-hidden /></span>
          <div>
            <h1 className="text-xl font-bold">Timetable Generator</h1>
            <p className="text-sm text-brand-100">Directorate of Examinations and Timetabling</p>
          </div>
        </div>
        <div className="space-y-4 p-8">
          <p className="text-sm text-muted">Sign in with the email and password from your Smart Attendance invitation.</p>
          <Field label="Email">
            <input type="email" className={inputClass} autoComplete="username" value={identifier} onChange={(e) => setIdentifier(e.target.value)} required />
          </Field>
          <Field label="Password">
            <input type="password" className={inputClass} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          {login.isError && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">{errorMessage(login.error)}</p>}
          <button type="submit" disabled={login.isPending} className={clsx(btn.primary, 'w-full py-3 text-base')}>
            {login.isPending ? 'Signing in…' : 'Sign in'}
          </button>
        </div>
      </form>
    </main>
  )
}
