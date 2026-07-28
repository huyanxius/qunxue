import { apiClient } from '../../api/client'
import { ApiRequestError } from '../../api/error'
import {
  createResearchTask as createResearchTaskRequest,
  getResearchTask as getResearchTaskRequest,
} from '../../api/generated'

/** SocioMatch 内部的 HTTP 适配器；模块调用方只从 index.ts 使用它。 */
export async function createResearchTask(idempotencyKey: string) {
  const { data, response } = await createResearchTaskRequest({
    client: apiClient,
    body: { entry_type: 'direct_input' },
    headers: { 'Idempotency-Key': idempotencyKey },
  })
  if (!data) {
    throw new ApiRequestError('研究任务创建失败。', response?.status)
  }
  return data
}

export async function getResearchTask(taskId: string) {
  const { data, response } = await getResearchTaskRequest({
    client: apiClient,
    path: { task_id: taskId },
  })
  if (!data) {
    throw new ApiRequestError('研究任务恢复失败。', response?.status)
  }
  return data
}
