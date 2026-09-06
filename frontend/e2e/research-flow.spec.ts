import { readFile } from 'node:fs/promises'

import { expect, test } from '@playwright/test'

import { SEED_FILE, type ResearchSeed } from './global-setup'

let seed: ResearchSeed

test.beforeAll(async () => {
  seed = JSON.parse(await readFile(SEED_FILE, 'utf8')) as ResearchSeed
})

test('research task routes to its stage and survives a reload', async ({ page }) => {
  const phenomenonField = page.getByLabel('现象表述')
  const taskLabel = page.getByText(`任务 ${seed.taskId.slice(0, 8)}`)
  const recoveryFailure = page.getByText(/暂时无法恢复这条现象候选|研究进度暂时无法恢复/)

  // Opening the bare task URL resolves to the correct stage route.
  await page.goto(`/research/${seed.taskId}`)
  await expect(page).toHaveURL(new RegExp(`/research/${seed.taskId}/phenomenon$`))
  await expect(taskLabel).toBeVisible()
  await expect(phenomenonField).toHaveValue(seed.phenomenon)
  await expect(recoveryFailure).toHaveCount(0)

  // A full reload recovers the same task id and the same input from the server.
  await page.reload()
  await expect(page).toHaveURL(new RegExp(`/research/${seed.taskId}/phenomenon$`))
  await expect(taskLabel).toBeVisible()
  await expect(phenomenonField).toHaveValue(seed.phenomenon)
  await expect(recoveryFailure).toHaveCount(0)
})
