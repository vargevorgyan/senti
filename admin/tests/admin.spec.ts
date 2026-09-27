import { createHmac } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const EMAIL = process.env.SENTI_ADMIN_EMAIL ?? 'admin@senti.local'
const PASSWORD = process.env.SENTI_ADMIN_PASSWORD ?? 'senti-admin'
const SHOTS = process.env.SENTI_SHOTS ?? 'test-results/shots'
const STATE = 'playwright-auth/session.json'
const TOTP = 'playwright-auth/totp.json'  // the authenticator secret the tests set up (or SENTI_ADMIN_TOTP_SECRET)

test.describe.configure({ mode: 'serial' })

function totp(secret: string, step: number): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const ch of secret.replace(/[\s=]/g, '').toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, '0')
  const key = Buffer.from(bits.match(/.{8}/g)!.map(b => parseInt(b, 2)))
  const msg = Buffer.alloc(8)
  msg.writeBigUInt64BE(BigInt(step))
  const mac = createHmac('sha1', key).update(msg).digest()
  const off = mac[mac.length - 1] & 0x0f
  return String((mac.readUInt32BE(off) & 0x7fffffff) % 1_000_000).padStart(6, '0')
}

async function freshCode(): Promise<string> {
  const saved = existsSync(TOTP) ? JSON.parse(readFileSync(TOTP, 'utf8')) : { secret: process.env.SENTI_ADMIN_TOTP_SECRET, last: 0 }
  if (!saved.secret) throw new Error('two-factor is already set up: pass SENTI_ADMIN_TOTP_SECRET')
  let now = Math.floor(Date.now() / 30000)
  while (saved.last >= now + 1) { await new Promise(r => setTimeout(r, 2000)); now = Math.floor(Date.now() / 30000) }  // a code can't be reused
  const step = Math.max(now, saved.last + 1)
  writeFileSync(TOTP, JSON.stringify({ ...saved, last: step }))
  return totp(saved.secret, step)
}

async function signIn(page: Page) {
  await page.goto('/')
  await page.getByLabel('Email').fill(EMAIL)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  const setup = page.getByRole('heading', { name: 'Protect this account with a second step' })
  const code = page.getByRole('heading', { name: 'Enter your code' })
  await expect(setup.or(code)).toBeVisible()
  if (await setup.isVisible()) {
    await page.screenshot({ path: `${SHOTS}/00b-two-factor-setup.png` })
    const secret = (await page.locator('code.mono').innerText()).replace(/\s/g, '')
    mkdirSync('playwright-auth', { recursive: true })
    writeFileSync(TOTP, JSON.stringify({ secret, last: 0 }))
  }
  await page.getByLabel('Code from your authenticator app').fill(await freshCode())
  await page.getByRole('button', { name: /Sign in|Turn on and sign in/ }).click()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
}

/** Reuse the session from the first test (the cookie is HttpOnly: the browser keeps it, page scripts can't read it). */
async function login(page: Page) {
  const state = JSON.parse(readFileSync(STATE, 'utf8'))
  await page.context().addCookies(state.cookies)
  await page.goto('/')
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
}

test('sign in with password and authenticator code', async ({ page }) => {
  await signIn(page)
  const cookies = await page.context().cookies()
  const session = cookies.find(c => c.name === 'senti_session')
  expect(session?.httpOnly && session.secure && session.sameSite === 'Strict').toBeTruthy()
  expect(await page.evaluate(() => document.cookie)).not.toContain('senti_session')  // invisible to page scripts
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('eyJ')  // no token in storage
  await page.context().storageState({ path: STATE })
})

test('wrong password shows a clear message', async ({ page }) => {
  await page.goto('/')
  await page.screenshot({ path: `${SHOTS}/00-login.png` })
  await page.getByLabel('Email').fill(EMAIL)
  await page.getByLabel('Password').fill('nope')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toContainText('don’t match')
})

test('every page renders', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await login(page)
  await expect(page.locator('.watch h1')).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/01-overview.png`, fullPage: true })
  for (const [name, heading, shot] of [
    ['Activity', 'Activity', '02-activity'], ['Approvals', 'Approvals', '03-approvals'], ['Profiles', 'Profiles', '04-profiles'],
    ['People and roles', 'People and roles', '06-people'], ['Devices', 'Devices', '07-devices'], ['Corporate judge', 'Corporate judge', '08-judge'],
    ['Change log', 'Change log', '09-changes'],
  ]) {
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name }).click()
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
    await page.waitForTimeout(400)
    await page.screenshot({ path: `${SHOTS}/${shot}.png`, fullPage: true })
  }
  expect(errors).toEqual([])
})

test('change a profile judge mode and save', async ({ page }) => {
  await login(page)
  await page.getByRole('link', { name: 'Profiles' }).click()
  await page.getByRole('link', { name: /Developer/ }).first().click()
  await expect(page.getByRole('heading', { level: 1, name: 'Developer' })).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/05-profile-editor.png`, fullPage: true })
  const current = await page.locator('.mode[aria-pressed="true"] b').innerText()
  const target = current.startsWith('Company AI') ? 'No AI judge' : 'Company AI'
  await page.getByRole('radio', { name: new RegExp(`^${target}`) }).click()
  await page.getByRole('button', { name: 'Save and push to Macs' }).click()
  await expect(page.getByRole('status')).toContainText('Saved version')
  // put it back
  await page.getByRole('radio', { name: new RegExp(`^${current.replace(/[()]/g, '.')}`) }).click()
  await page.getByRole('button', { name: 'Save and push to Macs' }).click()
  await expect(page.getByText('All changes saved')).toBeVisible()
})

test('dark theme', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /dark theme/i }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.screenshot({ path: `${SHOTS}/10-overview-dark.png`, fullPage: true })
  await page.getByRole('button', { name: /light theme/i }).click()
})

test('invite a person: one link, public join page', async ({ page, context }) => {
  await login(page)
  await page.getByRole('link', { name: 'People and roles' }).click()
  const email = `pw-${Date.now()}@acme.test`
  await page.getByPlaceholder('name@company.com').fill(email)
  await page.getByRole('button', { name: 'Add person and invite' }).click()
  const link = (await page.getByLabel('Invite link').innerText()).trim()
  expect(link).toMatch(/\/join#s=[^&]+&k=sti_[\w-]+(&fp=[0-9a-f]{64})?$/)
  await expect(page.getByLabel('Join command')).toContainText(`senti join '${link}'`)
  await page.screenshot({ path: `${SHOTS}/06b-invite.png`, fullPage: true })
  // the join page works signed out and makes no requests with the invite
  const anon = await context.browser()!.newContext({ ignoreHTTPSErrors: true })
  const p2 = await anon.newPage()
  const requests: string[] = []
  p2.on('request', r => requests.push(r.url()))
  await p2.goto(link)
  await expect(p2.getByRole('heading', { name: /invited to join/ })).toBeVisible()
  await expect(p2.getByLabel('Join command')).toContainText('senti join')
  await p2.screenshot({ path: `${SHOTS}/13-join-page.png`, fullPage: true })
  expect(requests.filter(u => u.includes('sti_'))).toEqual([])  // the key stays in the browser (after "#")
  await anon.close()
})

test('no content security policy violations', async ({ page }) => {
  const violations: string[] = []
  page.on('console', m => { if (/Content Security Policy|Refused to/i.test(m.text())) violations.push(m.text()) })
  await login(page)
  for (const name of ['Activity', 'Profiles', 'People and roles', 'Devices', 'Server gateway']) {
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name }).click()
    await page.waitForTimeout(300)
  }
  expect(violations).toEqual([])
})

test('corporate judge playground answers', async ({ page }) => {
  await login(page)
  await page.getByRole('link', { name: 'Corporate judge' }).click()
  await page.getByRole('button', { name: 'Ask the corporate judge' }).click()
  await expect(page.locator('.panel .al')).toBeVisible({ timeout: 60_000 })
  await page.screenshot({ path: `${SHOTS}/11-judge-result.png`, fullPage: true })
})

test('mobile layout', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page)
  await page.screenshot({ path: `${SHOTS}/12-mobile.png`, fullPage: true })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})
