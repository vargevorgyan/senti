import { useState } from 'react'
import { api } from '../api'
import { BarkWave } from '../components/ui'

type Step =
  | { kind: 'password' }
  | { kind: 'code'; token: string }
  | { kind: 'setup'; token: string; secret: string; qr: string }

export default function Login({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState<Step>({ kind: 'password' })
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submitPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      const r = await api<{ step: 'code' | 'setup'; token: string; secret?: string; qr?: string }>('/auth/login', { method: 'POST', body: { email, password } })
      setPassword(''); setCode('')
      setStep(r.step === 'setup' ? { kind: 'setup', token: r.token, secret: r.secret ?? '', qr: r.qr ?? '' } : { kind: 'code', token: r.token })
    } catch (e: any) {
      setErr(e.status === 401 ? 'That email and password don’t match an administrator.' : e.message)
    } finally { setBusy(false) }
  }

  const submitCode = async (e: React.FormEvent) => {
    e.preventDefault()
    if (step.kind === 'password') return
    setBusy(true); setErr('')
    try {
      await api(step.kind === 'setup' ? '/auth/two-factor/setup' : '/auth/login/code', { method: 'POST', body: { token: step.token, code } })
      onDone()
    } catch (e: any) {
      setErr(e.status === 401 && /sign in again|expired|token/i.test(e.message) ? 'That took too long. Sign in again.' : e.message)
      if (e.status === 401 && /sign in again|expired|token/i.test(e.message)) setStep({ kind: 'password' })
      setCode('')
    } finally { setBusy(false) }
  }

  const codeField = (
    <label className="field"><span>Code from your authenticator app</span>
      <input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" maxLength={7} value={code}
             onChange={e => setCode(e.target.value)} required autoFocus />
    </label>
  )

  return (
    <div className="login">
      <section className="art">
        <div>
          <h1>Senti</h1>
          <p>A watchdog for your team’s AI agents. Set what each role’s agents may do, see every decision, and answer the questions they escalate.</p>
        </div>
        <BarkWave />
      </section>
      {step.kind === 'password' && (
        <form onSubmit={submitPassword} aria-labelledby="signin">
          <h2 id="signin">Sign in to the admin panel</h2>
          <label className="field"><span>Email</span><input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required autoFocus /></label>
          <label className="field"><span>Password</span><input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
          {err && <div className="al info" role="alert"><p>{err}</p></div>}
          <button className="btn primary" type="submit" disabled={busy} style={{ justifyContent: 'center' }}>{busy ? 'Signing in…' : 'Sign in'}</button>
          <p className="small muted">Lost your password or authenticator? On the server, run <code>./senti-server reset-password</code>.</p>
        </form>
      )}
      {step.kind === 'code' && (
        <form onSubmit={submitCode} aria-labelledby="code-h">
          <h2 id="code-h">Enter your code</h2>
          <p className="muted">Open your authenticator app and type the 6-digit code for Senti.</p>
          {codeField}
          {err && <div className="al info" role="alert"><p>{err}</p></div>}
          <button className="btn primary" type="submit" disabled={busy} style={{ justifyContent: 'center' }}>{busy ? 'Checking…' : 'Sign in'}</button>
          <button className="btn ghost" type="button" onClick={() => { setStep({ kind: 'password' }); setErr('') }}>Back</button>
        </form>
      )}
      {step.kind === 'setup' && (
        <form onSubmit={submitCode} aria-labelledby="setup-h">
          <h2 id="setup-h">Protect this account with a second step</h2>
          <p className="muted">Whoever controls this account controls every Mac’s rules, so Senti asks for a code from your phone at every sign-in. Scan this with an authenticator app (1Password, Google Authenticator, Microsoft Authenticator…), then type the code it shows.</p>
          <img src={step.qr} alt="QR code to add Senti to your authenticator app" width={200} height={200} style={{ alignSelf: 'center', borderRadius: 12 }} />
          <p className="small muted">Can’t scan? Enter this key by hand: <code className="mono">{step.secret.replace(/(.{4})/g, '$1 ').trim()}</code></p>
          {codeField}
          {err && <div className="al info" role="alert"><p>{err}</p></div>}
          <button className="btn primary" type="submit" disabled={busy} style={{ justifyContent: 'center' }}>{busy ? 'Checking…' : 'Turn on and sign in'}</button>
        </form>
      )}
    </div>
  )
}
