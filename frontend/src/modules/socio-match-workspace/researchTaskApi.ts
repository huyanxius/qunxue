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
  ResearchTaskSource,
  ResearchTaskSubmission,
} from './researchTaskModel'

const taskSources = {
  user_input: 'user_input',
} satisfies Record<ResearchTaskResponse['source'], ResearchTaskSource>

function toResearchTask(response: ResearchTaskResponse): ResearchTask {
  return {
    taskId: response.task_id,
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

export async function submitResearchTaskViaApi(
  input: ResearchTaskSubmission,
): Promise<ResearchTask> {
  try {
    const { data, error, response } = await createResearchTaskRequest({
      client: apiClient,
      body: {
        phenomenon: input.phenomenon,
        research_intent: input.researchIntent,
        context: input.context,
      },
    })
    if (!data) {
      throw new ApiRequestError(
        extractErrorMessage(error, 'Research task creation failed.'),
        response?.status,
      )
    }
    return toResearchTask(data)
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw error
    }
    throw new ApiRequestError('The service could not save this task. Please retry.')
  }
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
        extractErrorMessage(error, 'Research task recovery failed.'),
        response?.status,
      )
    }
    return toResearchTask(data)
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw error
    }
    throw new ApiRequestError('The service could not restore this task. Please retry.')
  }
}
