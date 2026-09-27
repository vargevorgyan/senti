import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // ADMIN_BASE=/admin/ serves the panel under a sub-path (e.g. behind a site's reverse proxy)
  base: process.env.ADMIN_BASE ?? '/',
  plugins: [react()],
  // no data: URLs for fonts and images: the CSP only allows files from this server (font-src 'self')
  build: { assetsInlineLimit: 0 },
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.SENTI_API ?? 'http://localhost:8000', changeOrigin: true } },
  },
})
