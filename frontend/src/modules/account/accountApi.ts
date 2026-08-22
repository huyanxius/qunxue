import { apiClient } from '../../api/client'
import { ApiRequestError } from '../../api/error'
import { subscribeToSessionRejected } from '../../api/sessionEvents'
import {
  getCurrentSession,
  deleteResearchTask,
  listResearchTasks,
  loginSession,
  logoutSession,
  registerSession,
  type SessionResponse,
} from '../../api/generated'
import type { AccountSession, MyResearchItem } from './types'

export function watchSessionRejection(listener: () => void) {
  return subscribeToSessionRejected(listener)
}

function idempotencyKey() {
  return globalThis.crypto.randomUUID()
}

function toAccountSession(response: SessionResponse): AccountSession {
  return {
    sessionId: response.session_id,
    user: {
      userId: response.user.user_id,
      email: response.user.email,
      displayName: response.user.display_name,
    },
    expiresAt: response.expires_at,
  }
}

export async function getCurrentSessionViaApi(): Promise<AccountSession | null> {
  const { data, response } = await getCurrentSession({ client: apiClient })
  if (data) return toAccountSession(data)
  if (response?.status === 401) return null
  throw new ApiRequestError('登录状态读取失败。', response?.status)
}

export async function loginViaApi(
  email: string,
  password: string,
): Promise<AccountSession> {
  const { data, response } = await loginSession({
    client: apiClient,
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: { email, password },
  })
  if (!data) throw new ApiRequestError('邮箱或密码不正确。', response?.status)
  return toAccountSession(data)
}

export function isLoginServiceFailure(failure: unknown): boolean {
  return (
    failure instanceof ApiRequestError
    && failure.status !== 401
  )
}

export async function registerViaApi(
  email: string,
  password: string,
): Promise<AccountSession> {
  const { data, response } = await registerSession({
    client: apiClient,
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: { email, password, display_name: null },
  })
  if (!data) throw new ApiRequestError('账号创建失败，请稍后重试。', response?.status)
  return toAccountSession(data)
}

export async function logoutViaApi(): Promise<void> {
  const { data, response } = await logoutSession({
    client: apiClient,
    headers: { 'Idempotency-Key': idempotencyKey() },
  })
  if (!data) throw new ApiRequestError('退出失败，请稍后重试。', response?.status)
}

export async function listMyResearchViaApi(): Promise<MyResearchItem[]> {
  const { data, response } = await listResearchTasks({
    client: apiClient,
    query: { limit: 100 },
  })
  if (!data) throw new ApiRequestError('研究列表读取失败。', response?.status)
  return data.items.map((item) => {
    return {
      taskId: item.task_id,
      stageLabel: item.stage_label,
      nextActionLabel: item.next_action_label,
      entryPath: item.resume_path,
      blocker: item.blocker
        ? {
            action: item.blocker.action ?? null,
            code: item.blocker.code,
            message: item.blocker.message,
            recoverable: item.blocker.recoverable,
          }
        : null,
      retry: item.retry
        ? {
            action: item.retry.action,
            method: item.retry.method,
            href: item.retry.href,
            label: item.retry.label,
          }
        : null,
      phenomenonSummary: item.phenomenon_summary?.phenomenon ?? '尚未确认现象',
      adoptedTheoryCount: item.adopted_theory_count,
      createdAt: item.created_at,
      updatedAt: item.updated_at,
    }
  })
}

export async function deleteMyResearchViaApi(taskId: string): Promise<void> {
  const { data, response } = await deleteResearchTask({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
  })
  if (!data) throw new ApiRequestError('研究删除失败。', response?.status)
}
