import { apiClient } from '../../api/client'
import { ApiRequestError } from '../../api/error'
import {
  createResearchTask as createResearchTaskRequest,
  getResearchTask as getResearchTaskRequest,
  type ErrorResponse,
  type HttpValidationError,
  type ResearchTaskResponse,
} from '../../api/generated'
import type {
  ResearchTask,
  ResearchTaskAction,
  ResearchTaskEntryType,
  ResearchTaskSource,
  ResearchTaskStatus,
  ResearchTaskSubmission,
} from './researchTaskModel'

const entryTypes = {
  direct_input: 'direct_input',
} satisfies Record<ResearchTaskResponse['entry_type'], ResearchTaskEntryType>

const taskStatuses = {
  draft: 'draft',
} satisfies Record<ResearchTaskResponse['status'], ResearchTaskStatus>

const taskActions = {
  submit_phenomenon: 'submit_phenomenon',
} satisfies Record<
  ResearchTaskResponse['allowed_actions'][number],
  ResearchTaskAction
>

const taskSources = {
  user_input: 'user_input',
} satisfies Record<ResearchTaskResponse['source'], ResearchTaskSource>

type ResearchTaskResponseCompat = Partial<
  Pick<
    ResearchTaskResponse,
    'entry_type' | 'status' | 'version' | 'allowed_actions'
  >
> &
  ResearchTaskResponse

async function buildIdempotencyKey(
  input: ResearchTaskSubmission,
): Promise<string> {
  const payload = JSON.stringify({
    phenomenon: input.phenomenon,
    researchIntent: input.researchIntent ?? null,
    context: input.context ?? null,
  })
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(payload),
  )

  return Array.from(new Uint8Array(digest).slice(0, 16), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('')
}

function toResearchTask(response: ResearchTaskResponse): ResearchTask {
  const compatResponse = response as ResearchTaskResponseCompat
  const allowedActionIds = compatResponse.allowed_actions ?? ['submit_phenomenon']

  return {
    taskId: response.task_id,
    entryType: entryTypes[compatResponse.entry_type ?? 'direct_input'],
    status: taskStatuses[compatResponse.status ?? 'draft'],
    version: compatResponse.version ?? 1,
    allowedActions: allowedActionIds.map((action) => taskActions[action]),
    phenomenon: response.phenomenon,
    researchIntent: response.research_intent ?? null,
    context: response.context ?? null,
    source: taskSources[response.source],
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  }
}

function isErrorResponse(error: unknown): error is ErrorResponse {
  return Boolean(
    error &&
      typeof error === 'object' &&
      'error' in error &&
      error.error &&
      typeof error.error === 'object' &&
      'message' in error.error,
  )
}

function isValidationError(error: unknown): error is HttpValidationError {
  return Boolean(
    error && typeof error === 'object' && 'detail' in error,
  )
}

function extractErrorMessage(error: unknown, fallback: string): string {
  if (isErrorResponse(error)) {
    return error.error.message
  }
  if (isValidationError(error) && error.detail && error.detail.length > 0) {
    return error.detail.map((detail) => detail.msg).join('; ')
  }
  return fallback
}

export async function createResearchTaskViaApi(
  input: ResearchTaskSubmission,
): Promise<ResearchTask> {
  try {
    const idempotencyKey = await buildIdempotencyKey(input)
    const { data, error, response } = await createResearchTaskRequest({
      client: apiClient,
      body: {
        phenomenon: input.phenomenon,
        research_intent: input.researchIntent,
        context: input.context,
      },
      headers: { 'Idempotency-Key': idempotencyKey },
    })
    if (!data) {
      throw new ApiRequestError(
        extractErrorMessage(error, '研究任务创建失败。'),
        response?.status,
      )
    }
    return toResearchTask(data)
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw error
    }
    throw new ApiRequestError('服务暂时无法保存该任务，请稍后重试。')
  }
}

export async function submitResearchTaskViaApi(
  input: ResearchTaskSubmission,
): Promise<ResearchTask> {
  return createResearchTaskViaApi(input)
}

export async function getResearchTaskViaApi(
  taskId: string,
): Promise<ResearchTask> {
  try {
    const { data, error, response } = await getResearchTaskRequest({
      client: apiClient,
      path: { task_id: taskId },
    })
    if (!data) {
      throw new ApiRequestError(
        extractErrorMessage(error, '研究任务恢复失败。'),
        response?.status,
      )
    }
    return toResearchTask(data)
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw error
    }
    throw new ApiRequestError('服务暂时无法恢复该任务，请稍后重试。')
  }
}