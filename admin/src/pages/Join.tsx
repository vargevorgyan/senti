import { useEffect, useState } from 'react'
import { BarkWave } from '../components/ui'

const DEFAULT_INSTALLER = 'https://raw.githubusercontent.com/vargevorgyan/senti/main/engine/install.sh'

/** Public invite landing page. It reads the invite from the part of the link after "#", which browsers never send to any
 *  server. Its only request asks this server where the Mac installer comes from (nothing about the invite is sent). */
function parse(hash: string): { server: string; key: string; fp: string; ok: boolean } {
  const q = new URLSearchParams(hash.replace(/^#/, ''))
  const server = q.get('s') ?? ''
  const key = q.get('k') ?? ''
  const fp = q.get('fp') ?? ''
  const ok = /^(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.-]{1,253})(:\d{1,5})?$/.test(server) && /^sti_[A-Za-z0-9_-]{20,100}$/.test(key)
    && (!fp || /^[0-9a-f]{64}$/.test(fp))
  return { server, key, fp, ok }
}

export default function Join() {
  const { server, key, fp, ok } = parse(window.location.hash)
  // Rebuilt only from the validated parts (letters, digits, - _ . : [ ]): nothing else from the address, such as a query
  // string with quotes, can end up in the command a person pastes into Terminal.
  const link = `${window.location.origin}/join#s=${server}&k=${key}${fp ? `&fp=${fp}` : ''}`
  const [installer, setInstaller] = useState(DEFAULT_INSTALLER)
  useEffect(() => {
    fetch('/api/v1/installer').then(r => r.ok ? r.json() : null).then(j => {
      if (j?.url === '/install.sh') setInstaller(`${window.location.origin}/install.sh`)
      else if (typeof j?.url === 'string' && /^https:\/\/[A-Za-z0-9.:/_~%-]+$/.test(j.url)) setInstaller(j.url)
    }).catch(() => { /* keep the default */ })
  }, [])
  const command = `curl -fsSL ${installer} | sh -s -- '${link}'`
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
            <p>Server <b>{server}</b>. Open Terminal on your Mac and paste this one line. It installs Senti and joins:</p>
            <div className="copy"><pre className="mono" aria-label="Join command" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{command}</pre>
              <button className="btn" type="button" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button></div>
            <p className="small muted">It installs Senti in your user account (no administrator password), checks that the server matches your invite, then shows you the company name and your email as the server reports them, and joins only after you say yes. If the name isn't your company, stop and tell your administrator.</p>
            <p className="small muted">The invite works once, on one Mac, and expires after 48 hours. Senti already installed? Run <code className="mono">senti join '…'</code> with the same link.</p>
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
