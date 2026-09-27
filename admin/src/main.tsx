import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@fontsource-variable/bricolage-grotesque'
import '@fontsource-variable/dm-sans'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import App from './App'
import './styles.css'

// Built for a sub-path (ADMIN_BASE=/admin/): send stray visits to it
const base = import.meta.env.BASE_URL.replace(/\/$/, '')
// the public join page stays at /join (invite links point there) and needs no router
const isJoin = window.location.pathname === '/join'
if (base && !isJoin && !window.location.pathname.startsWith(base)) window.location.replace(`${base}/`)

createRoot(document.getElementById('root')!).render(
  <StrictMode>{isJoin ? <App /> : <BrowserRouter basename={base || undefined}><App /></BrowserRouter>}</StrictMode>,
)
