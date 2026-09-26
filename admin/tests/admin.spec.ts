import { expect, test, type Page } from '@playwright/test'

const EMAIL = process.env.SENTI_ADMIN_EMAIL ?? 'admin@senti.local'
const PASSWORD = process.env.SENTI_ADMIN_PASSWORD ?? 'senti-admin'
const SHOTS = process.env.SENTI_SHOTS ?? 'test-results/shots'

async function login(page: Page) {
  await page.goto('/')
  await page.getByLabel('Email').fill(EMAIL)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
}

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
  const target = current === 'Corporate judge' ? 'Local judge' : 'Corporate judge'
  await page.getByRole('radio', { name: new RegExp(target) }).click()
  await page.getByRole('button', { name: 'Save and push to Macs' }).click()
  await expect(page.getByRole('status')).toContainText('Saved version')
  // put it back
  await page.getByRole('radio', { name: new RegExp(current) }).click()
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

test('create an enrollment code', async ({ page }) => {
  await login(page)
  await page.getByRole('link', { name: 'Devices' }).click()
  await page.getByRole('button', { name: 'New enrollment code' }).click()
  await expect(page.getByRole('status')).toContainText('New code created')
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
