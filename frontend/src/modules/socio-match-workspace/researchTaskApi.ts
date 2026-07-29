import { apiClient } from '../../api/client'
import { ApiRequestError } from '../../api/error'
import {
  createResearchTask as createResearchTaskRequest,
  getResearchTask as getResearchTaskRequest,
  type ResearchTaskResponse,
} from '../../api/generated'
import type {
  ResearchTask,
  ResearchTaskAction,
  ResearchTaskEntryType,
  ResearchTaskStatus,
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

function toResearchTask(response: ResearchTaskResponse): ResearchTask {
  return {
    taskId: response.task_id,
    entryType: entryTypes[response.entry_type],
    status: taskStatuses[response.status],
    version: response.version,
    allowedActions: response.allowed_actions.map(
      (action) => taskActions[action],
    ),
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  }
}

/** SocioMatch 内部的 HTTP 适配器；公共入口不得直接导出本文件。 */
export async function createResearchTaskViaApi(
  idempotencyKey: string,
): Promise<ResearchTask> {
  const { data, response } = await createResearchTaskRequest({
    client: apiClient,
    body: { entry_type: 'direct_input' },
    headers: { 'Idempotency-Key': idempotencyKey },
  })
  if (!data) {
    throw new ApiRequestError('研究任务创建失败。', response?.status)
  }
  return toResearchTask(data)
}

export async function getResearchTaskViaApi(
  taskId: string,
): Promise<ResearchTask> {
  const { data, response } = await getResearchTaskRequest({
    client: apiClient,
    path: { task_id: taskId },
  })
  if (!data) {
    throw new ApiRequestError('研究任务恢复失败。', response?.status)
  }
  return toResearchTask(data)
}
