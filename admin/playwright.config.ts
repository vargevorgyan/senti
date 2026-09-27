import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  use: { baseURL: process.env.SENTI_ADMIN_URL ?? 'https://localhost:8443', ignoreHTTPSErrors: true, viewport: { width: 1440, height: 960 }, screenshot: 'only-on-failure' },
  reporter: [['list']],
})
