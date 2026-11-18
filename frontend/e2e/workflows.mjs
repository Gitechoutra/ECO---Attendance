/**
 * Browser end-to-end workflow test (Playwright + locally installed Chrome).
 * Run against a TEST deployment (it creates a department, an employee and a leave request):
 *   E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... npm run e2e
 */
import { chromium } from 'playwright-core'
const BASE = process.env.E2E_BASE_URL || 'http://localhost:5173'
const OUT = process.argv[2] || '.'
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const errors = []
const step = (m) => console.log('✓', m)
const stamp = Date.now().toString().slice(-6)
const field = (page, label, scope = page) => scope.locator(`label:text-is("${label}")`).locator('xpath=following-sibling::*[1]').locator('xpath=descendant-or-self::*[self::input or self::select or self::textarea][1]')

async function newPage(viewport = { width: 1366, height: 860 }) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => { if (m.type() === 'error' && !m.text().includes('401')) errors.push(`console: ${m.text().slice(0, 160)}`) })
  return { ctx, page }
}
async function login(page, email, pw) {
  await page.goto(`${BASE}/login`)
  await page.fill('#email', email); await page.fill('#password', pw)
  await page.click('button[type=submit]')
}

try {
  // ---- admin: department + employee
  const A = await newPage()
  await login(A.page, process.env.E2E_ADMIN_EMAIL, process.env.E2E_ADMIN_PASSWORD)
  await A.page.waitForURL(`${BASE}/`)
  step('admin signed in')
  await A.page.goto(`${BASE}/admin/organization`)
  await A.page.click('button:has-text("New department")')
  await A.page.fill('#f-name', `QA Dept ${stamp}`); await A.page.fill('#f-code', `Q${stamp}`)
  await A.page.click('button[form=form-modal]')
  await A.page.waitForSelector(`text=QA Dept ${stamp}`)
  step('department created via form')

  await A.page.goto(`${BASE}/employees`)
  await A.page.click('button:has-text("Add employee")')
  const dr = A.page.locator('[role=dialog]')
  await field(A.page, 'First name', dr).fill('Priya')
  await field(A.page, 'Last name', dr).fill(`Tester${stamp}`)
  await field(A.page, 'Work email', dr).fill(`priya.${stamp}@example.com`)
  await field(A.page, 'Joining date', dr).fill('2025-04-01')
  await field(A.page, 'Department', dr).selectOption({ label: `QA Dept ${stamp}` })
  await A.page.click('button:has-text("Create employee")')
  await A.page.waitForSelector('text=Temporary password')
  const pw = (await A.page.locator('code').first().innerText()).trim()
  await A.page.screenshot({ path: `${OUT}/e2e-temp-password.png` })
  await A.page.click('button:has-text("Done")')
  step(`employee created, temp password shown (${pw.length} chars)`)

  // ---- new employee: forced password change, apply leave
  const E = await newPage({ width: 390, height: 844 })
  await login(E.page, `priya.${stamp}@example.com`, pw)
  await E.page.waitForURL(`${BASE}/change-password`)
  step('first login forced to change password')
  const inputs = E.page.locator('input[type=password]')
  await inputs.nth(0).fill(pw); await inputs.nth(1).fill('Welcome2Echo'); await inputs.nth(2).fill('Welcome2Echo')
  await E.page.click('button:has-text("Update password")')
  await E.page.waitForURL(`${BASE}/`)
  step('password changed, landed on dashboard (mobile)')
  await E.page.goto(`${BASE}/leave`)
  await E.page.click('button:has-text("Apply leave") >> nth=0')
  const today = new Date(); const d = new Date(today.getTime() + 21 * 864e5)
  const iso = d.toISOString().slice(0, 10)
  await E.page.selectOption('#f-leave_type_id', { label: 'Casual Leave' })
  await E.page.fill('#f-start_date', iso); await E.page.fill('#f-end_date', iso)
  await E.page.fill('#f-reason', 'E2E test leave')
  await E.page.click('button[form=form-modal]')
  await E.page.waitForSelector('text=Leave requested')
  await E.page.screenshot({ path: `${OUT}/e2e-mobile-leave.png` })
  step('leave applied from mobile')
  // mobile nav drawer
  await E.page.click('button[aria-label="Open menu"]')
  await E.page.locator('aside:visible').getByText('Payroll').waitFor(); await E.page.waitForTimeout(500)
  await E.page.screenshot({ path: `${OUT}/e2e-mobile-drawer.png` })
  step('mobile navigation drawer opens')

  // ---- admin approves
  await A.page.goto(`${BASE}/leave?tab=approvals`)
  const row = A.page.locator(`tr:has-text("Tester${stamp}")`)
  await row.locator('button:has-text("Approve")').click()
  await A.page.waitForSelector('text=Leave approved')
  step('admin approved leave from approvals queue')
  await E.page.goto(`${BASE}/leave`)
  await E.page.locator('text=Approved >> visible=true').first().waitFor()
  step('employee sees approved status')
  // ---- global search
  await A.page.keyboard.press('Control+k')
  await A.page.keyboard.type(`Tester${stamp}`)
  await A.page.waitForSelector(`[role=dialog] >> text=Priya Tester${stamp}`)
  step('global search finds new employee')
} catch (e) {
  console.log('✗ FAILED:', e.message.split('\n')[0])
  process.exitCode = 1
} finally {
  console.log(errors.length ? errors.join('\n') : 'NO_CONSOLE_ERRORS')
  await browser.close()
}
