import { test, expect } from '@playwright/test'

async function openJobs(page: import('@playwright/test').Page) {
  await page.goto('/')
  await page.getByRole('navigation').getByRole('button', { name: 'Jobs', exact: true }).click()
}

test('imports a job with only a URL and offers source review', async ({ page }) => {
  const postingUrl = 'https://careers.example.com/jobs/python-engineer'
  let submitted: unknown
  await page.route('**/api/v1/jobs/import-url', async (route) => {
    submitted = route.request().postDataJSON()
    await route.fulfill({ status: 201, json: {
      id: 'url-import-fixture', title: 'Imported Python Engineer', company: 'Fixture Studio',
      url: postingUrl, source: 'url', created_at: new Date().toISOString(),
      raw_description: 'Develop reliable Python services. SQL experience required.',
      requirements: [{ id: 'url-requirement', text: 'Python', normalized_term: 'python', kind: 'skill', priority: 'required', confirmed: false }],
    } })
  })
  await openJobs(page)
  await expect(page.getByRole('heading', { name: 'Found a role you love?' })).toBeVisible()
  await expect(page.getByLabel('Company', { exact: true })).toBeHidden()
  await page.getByRole('textbox', { name: 'Job posting URL' }).fill(postingUrl)
  await page.getByRole('button', { name: 'Import job', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Job imported.')
  expect(submitted).toEqual({ url: postingUrl })
  await expect(page.getByRole('heading', { name: 'Imported Python Engineer · Fixture Studio' })).toBeVisible()
  await expect(page.getByLabel('Requirement 1', { exact: true })).toHaveValue('Python')
  await expect(page.getByRole('checkbox', { name: 'Confirmed', exact: true })).not.toBeChecked()
  await page.getByText('Original job description and posting details', { exact: true }).click()
  await expect(page.getByLabel('Posting URL', { exact: true })).toHaveValue(postingUrl)
  await expect(page.locator('.job-description')).toContainText('Develop reliable Python services.')
})

test('blocked URL import keeps user input and opens the manual fallback', async ({ page }) => {
  await page.route('**/api/v1/jobs/import-url', route => route.fulfill({
    status: 422, json: { detail: 'This site blocked the request. Paste the job text instead.' },
  }))
  await openJobs(page)
  await page.getByText('Paste job text instead', { exact: true }).click()
  await page.getByLabel('Company', { exact: true }).fill('Keep my company')
  await page.getByLabel('Role title', { exact: true }).fill('Keep my title')
  await page.getByText('Paste job text instead', { exact: true }).click()
  await page.getByLabel('Job posting URL', { exact: true }).fill('https://example.com/blocked')
  await page.getByRole('button', { name: 'Import job', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Paste the job text instead.')
  await expect(page.getByLabel('Job posting URL', { exact: true })).toHaveValue('https://example.com/blocked')
  await expect(page.getByLabel('Company', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Company', { exact: true })).toHaveValue('Keep my company')
  await expect(page.getByLabel('Role title', { exact: true })).toHaveValue('Keep my title')
})
