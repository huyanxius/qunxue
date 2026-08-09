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
  type ResearchTaskNavigationAction,
  type ResearchTaskNavigationResponse,
} from '../../api/generated'
import type { AccountSession, MyResearchItem } from './types'

const stagePresentation = {
  phenomenon_input: 'phenomenon',
  phenomenon_confirmation: 'phenomenon',
  theory_matching: 'match',
  theory_decision: 'match',
  framework_drafting: 'framework',
  framework_review: 'framework',
  completed: 'framework',
} satisfies Record<
  ResearchTaskNavigationResponse['current_stage'],
  string
>

const stageLabelByAction = {
  submit_phenomenon: '草稿',
  confirm_phenomenon: '现象待确认',
  start_matching: '现象已确认',
  review_theory_candidates: '匹配生成中',
  confirm_theory_plan: '已有决策',
  create_framework: '已有决策',
  review_framework: '框架草稿',
  confirm_framework: '框架草稿',
  export: '框架已确认',
} satisfies Record<ResearchTaskNavigationAction, string>

const actionLabels = {
  submit_phenomenon: '补充材料',
  confirm_phenomenon: '确认现象',
  start_matching: '开始理论匹配',
  review_theory_candidates: '查看候选理论',
  confirm_theory_plan: '确认理论选择',
  create_framework: '形成研究框架',
  review_framework: '审校研究框架',
  confirm_framework: '确认研究框架',
  export: '导出研究记录',
} satisfies Record<ResearchTaskNavigationAction, string>

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
    && failure.status !== undefined
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
    const route = stagePresentation[item.current_stage]
    const action = item.allowed_actions[0]!
    return {
      taskId: item.task_id,
      stageLabel: stageLabelByAction[action],
      nextActionLabel: actionLabels[action],
      entryPath: `/research/${item.task_id}/${route}`,
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
