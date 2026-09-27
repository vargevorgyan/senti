import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api, token } from './api'
import { Icon, LiveProvider, ToastProvider, useLive, useLiveEvent, useToast } from './components/ui'
import Activity from './pages/Activity'
import Approvals from './pages/Approvals'
import ChangeLog from './pages/ChangeLog'
import Devices from './pages/Devices'
import Judge from './pages/Judge'
import Login from './pages/Login'
import Overview from './pages/Overview'
import People from './pages/People'
import ProfileEditor from './pages/ProfileEditor'
import Profiles from './pages/Profiles'

function useTheme() {
  const [theme, setTheme] = useState<string>(() => { try { return localStorage.getItem('senti.theme') ?? '' } catch { return '' } })
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme
    else delete document.documentElement.dataset.theme
    try { localStorage.setItem('senti.theme', theme) } catch { /* private mode */ }
  }, [theme])
  const dark = theme ? theme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  return { dark, toggle: () => setTheme(dark ? 'light' : 'dark') }
}

function Shell({ onLogout }: { onLogout: () => void }) {
  const { connected } = useLive()
  const { dark, toggle } = useTheme()
  const [me, setMe] = useState<{ email: string } | null>(null)
  const [org, setOrg] = useState('')
  const [pending, setPending] = useState(0)
  const refresh = () => api('/admin/approvals?status=pending').then((a: unknown[]) => setPending(a.length)).catch(() => {})
  useEffect(() => {
    api('/auth/me').then(setMe).catch(() => {})
    api('/admin/overview').then(o => setOrg(o.org)).catch(() => {})
    refresh()
  }, [])
  useLiveEvent(m => { if (m.type === 'approval') refresh() })
  const toast = useToast()
  const changePassword = async () => {
    const current = window.prompt('Current password')
    if (!current) return
    const next = window.prompt('New password (at least 8 characters)')
    if (!next) return
    try {
      const r = await api<{ token: string }>('/auth/password', { method: 'PUT', body: { current, new: next } })
      token.set(r.token)
      toast('Password changed. Every other session was signed out.')
    } catch (e: any) { toast(e.message, true) }
  }
  const logoutAll = async () => {
    if (!confirm('Sign out every session of this account, including this one?')) return
    await api('/auth/logout-all', { method: 'POST' }).catch(() => {})
    onLogout()
  }
  const nav = [
    { to: '/', icon: 'home', label: 'Overview', end: true },
    { to: '/activity', icon: 'activity', label: 'Activity' },
    { to: '/approvals', icon: 'approve', label: 'Approvals', count: pending },
    { to: '/profiles', icon: 'shield', label: 'Profiles' },
    { to: '/people', icon: 'people', label: 'People and roles' },
    { to: '/devices', icon: 'laptop', label: 'Devices' },
    { to: '/judge', icon: 'brain', label: 'Corporate judge' },
    { to: '/changes', icon: 'log', label: 'Change log' },
  ]
  return (
    <div className="shell">
      <aside className="rail">
        <NavLink to="/" className="brand" aria-label="Senti overview"><img src="/senti-app-icon.svg" alt="" /><b>Senti</b></NavLink>
        <nav className="nav" aria-label="Main">
          {nav.map(n => (
            <NavLink key={n.to} to={n.to} end={n.end}><Icon name={n.icon} />{n.label}{n.count ? <span className="count">{n.count}</span> : null}</NavLink>
          ))}
        </nav>
        <div className="rail-foot">
          <span>{me?.email}</span>
          <button type="button" onClick={changePassword}>Change password</button>
          <button type="button" onClick={onLogout}>Sign out</button>
          <button type="button" onClick={logoutAll}>Sign out everywhere</button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <span className="org">{org}</span>
          <span className={`live${connected ? '' : ' off'}`}><i />{connected ? 'Live' : 'Reconnecting'}</span>
          <span className="spacer" />
          <button type="button" className="btn ghost sm" onClick={toggle} aria-label={dark ? 'Use light theme' : 'Use dark theme'}>
            <Icon name={dark ? 'sun' : 'moon'} size={16} />{dark ? 'Light' : 'Dark'}
          </button>
        </header>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/approvals" element={<Approvals />} />
          <Route path="/profiles" element={<Profiles />} />
          <Route path="/profiles/:id" element={<ProfileEditor />} />
          <Route path="/people" element={<People />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/judge" element={<Judge />} />
          <Route path="/changes" element={<ChangeLog />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </div>
  )
}

export default function App() {
  const [authed, setAuthed] = useState(!!token.get())
  useEffect(() => {
    const out = () => setAuthed(false)
    window.addEventListener('senti:logout', out)
    return () => window.removeEventListener('senti:logout', out)
  }, [])
  return (
    <ToastProvider>
      {authed
        ? <LiveProvider><Shell onLogout={() => { token.clear(); setAuthed(false) }} /></LiveProvider>
        : <Login onDone={() => setAuthed(true)} />}
    </ToastProvider>
  )
}
