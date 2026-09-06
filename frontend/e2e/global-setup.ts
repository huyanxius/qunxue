import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { request, type FullConfig } from '@playwright/test'

const HERE = dirname(fileURLToPath(import.meta.url))
export const ARTIFACT_DIR = resolve(HERE, '.artifacts')
export const STORAGE_STATE = resolve(ARTIFACT_DIR, 'storage-state.json')
export const SEED_FILE = resolve(ARTIFACT_DIR, 'seed.json')

const API_PORT = process.env.QUNXUE_E2E_PORT ?? '8000'
const API_ORIGIN = `http://127.0.0.1:${API_PORT}`

export type ResearchSeed = {
  readonly taskId: string
  readonly phenomenon: string
  readonly resumePath: string
}

function idempotencyKey(): string {
  return `e2e-${crypto.randomUUID()}`
}

/**
 * Seed one authenticated user and one research task with a confirmed phenomenon
 * input, entirely through the real HTTP API. The browser spec then only has to
 * verify the user-visible part: routing into the task and recovering it on reload.
 */
async function globalSetup(_config: FullConfig): Promise<void> {
  await mkdir(ARTIFACT_DIR, { recursive: true })

  const api = await request.newContext({ baseURL: API_ORIGIN })

  const email = `e2e-${Date.now()}-${crypto.randomUUID()}@example.com`
  const register = await api.post('/api/session/register', {
    headers: { 'Idempotency-Key': idempotencyKey() },
    data: { email, password: 'research-passphrase' },
  })
  if (register.status() !== 201) {
    throw new Error(`register failed: ${register.status()} ${await register.text()}`)
  }

  const created = await api.post('/api/research-tasks', {
    headers: { 'Idempotency-Key': idempotencyKey() },
    data: { entry_type: 'direct_input' },
  })
  if (created.status() !== 201) {
    throw new Error(`create task failed: ${created.status()} ${await created.text()}`)
  }
  const taskId = (await created.json()).task_id as string

  // A sentence that matches no built-in Mock case, so it round-trips verbatim
  // into the phenomenon candidate and is a stable anchor for the reload check.
  const phenomenon = `E2E 关键链路校验 ${crypto.randomUUID().slice(0, 8)}：社区互助网络的代际变化`

  const directInput = await api.post(`/api/research-tasks/${taskId}/inputs/direct`, {
    headers: { 'Idempotency-Key': idempotencyKey() },
    data: { phenomenon, research_intent: '验证创建与刷新恢复链路', context: '端到端测试' },
  })
  if (directInput.status() !== 200) {
    throw new Error(`direct input failed: ${directInput.status()} ${await directInput.text()}`)
  }

  const extracted = await api.post(`/api/research-tasks/${taskId}/phenomenon-candidates`, {
    headers: { 'Idempotency-Key': idempotencyKey() },
    data: { expected_task_version: 1, requested_count: 1 },
  })
  if (extracted.status() !== 200) {
    throw new Error(`extract candidates failed: ${extracted.status()} ${await extracted.text()}`)
  }

  await api.storageState({ path: STORAGE_STATE })
  await api.dispose()

  const seed: ResearchSeed = {
    taskId,
    phenomenon,
    resumePath: `/research/${taskId}/phenomenon`,
  }
  await writeFile(SEED_FILE, JSON.stringify(seed, null, 2), 'utf8')
}

export default globalSetup
