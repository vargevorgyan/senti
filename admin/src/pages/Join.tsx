import { useState } from 'react'
import { BarkWave } from '../components/ui'

/** Public invite landing page. Static: it reads the invite from the part of the link after "#", which browsers never
 *  send to any server, and it makes no requests at all. */
function parse(hash: string): { server: string; ok: boolean } {
  const q = new URLSearchParams(hash.replace(/^#/, ''))
  const server = q.get('s') ?? ''
  const key = q.get('k') ?? ''
  const fp = q.get('fp') ?? ''
  const ok = /^(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.-]{1,253})(:\d{1,5})?$/.test(server) && /^sti_[A-Za-z0-9_-]{20,100}$/.test(key)
    && (!fp || /^[0-9a-f]{64}$/.test(fp))
  return { server, ok }
}

export default function Join() {
  const { server, ok } = parse(window.location.hash)
  const command = `senti join '${window.location.href}'`
  const [copied, setCopied] = useState(false)
  const copy = () => navigator.clipboard.writeText(command).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 2500) })
  return (
    <div className="login">
      <section className="art">
        <div>
          <h1>Senti</h1>
          <p>Your company uses Senti to keep AI assistants on your Mac from doing risky things by mistake. It checks each action before it runs and stays quiet when things are safe.</p>
        </div>
        <BarkWave />
      </section>
      <div className="join" aria-labelledby="join-h" style={{ display: 'grid', gap: 16, alignContent: 'center', padding: 'clamp(24px, 5vw, 64px)', maxWidth: 560 }}>
        {ok ? (
          <>
            <h2 id="join-h">You're invited to join a Senti server</h2>
            <p>Server <b>{server}</b>. Open Terminal on your Mac and paste this line:</p>
            <div className="copy"><pre className="mono" aria-label="Join command" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{command}</pre>
              <button className="btn" type="button" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button></div>
            <p className="small muted">Senti will show you the company name and your email as the server reports them, and join only after you say yes. If the name isn't your company, stop and tell your administrator.</p>
            <p className="small muted">The invite works once, on one Mac, and expires after 48 hours. Senti isn't installed yet? Ask your administrator for the installer.</p>
          </>
        ) : (
          <>
            <h2 id="join-h">This invite link is incomplete</h2>
            <p>Copy the whole link from your invite, including everything after the “#”, or ask your administrator for a new invite.</p>
          </>
        )}
      </div>
    </div>
  )
}
