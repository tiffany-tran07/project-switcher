import { test, expect } from '@playwright/test'

test('career library tabs have specific titles and achievement terminology', async ({ page }) => {
  await page.goto('/')
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  const achievements = navigation.getByRole('button', { name: 'Achievements', exact: true })
  await expect(navigation.getByRole('button', { name: 'Evidence', exact: true })).toHaveCount(0)
  await expect(achievements.locator('svg path')).toHaveAttribute('d', 'M19 8a7 7 0 1 1-14 0 7 7 0 0 1 14 0 M8 14l-2 8 6-3 6 3-2-8')

  for (const [tab, title] of [
    ['Achievements', 'Your achievements.'],
    ['Experiences', 'Your work experience.'],
    ['Projects', 'Your projects.'],
    ['Skills', 'Your skills.'],
    ['Profile', 'Your profile.'],
  ]) {
    const button = navigation.getByRole('button', { name: tab, exact: true })
    await button.click()
    await expect(button).toHaveAttribute('aria-current', 'page')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(title)
    await expect(page.locator('.workspace-topbar strong')).toHaveText(tab)
  }
  await achievements.click()
  await page.getByRole('button', { name: '+ New', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'New achievement', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save achievement', exact: true })).toBeVisible()
})
