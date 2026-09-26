import { useState } from 'react'
import { api, token } from '../api'
import { BarkWave } from '../components/ui'

export default function Login({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      const r = await api<{ token: string }>('/auth/login', { method: 'POST', body: { email, password } })
      token.set(r.token)
      onDone()
    } catch (e: any) {
      setErr(e.status === 401 ? 'That email and password don’t match an administrator.' : `Sign-in failed: ${e.message}`)
    } finally { setBusy(false) }
  }
  return (
    <div className="login">
      <section className="art">
        <div>
          <h1>Senti</h1>
          <p>A watchdog for your team’s AI agents. Set what each role’s agents may do, see every decision, and answer the questions they escalate.</p>
        </div>
        <BarkWave />
      </section>
      <form onSubmit={submit} aria-labelledby="signin">
        <h2 id="signin">Sign in to the admin panel</h2>
        <label className="field"><span>Email</span><input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required autoFocus /></label>
        <label className="field"><span>Password</span><input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
        {err && <div className="al info" role="alert"><p>{err}</p></div>}
        <button className="btn primary" type="submit" disabled={busy} style={{ justifyContent: 'center' }}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="small muted">The first administrator is set with SENTI_ADMIN_EMAIL and SENTI_ADMIN_PASSWORD when the backend starts.</p>
      </form>
    </div>
  )
}
