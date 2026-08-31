import { apiClient } from './client'
import { ApiRequestError } from './error'
import { getHealth, type HealthResponse } from './generated'

export interface SystemHealth {
  readonly capability: 'unavailable' | 'mock' | 'base' | 'sft'
  readonly contractVersion: string
  readonly knowledgeReleaseId: string | null
  readonly modelVersion: string
  readonly persistence: 'sqlite'
  readonly provider: string
  readonly runtimeMode: 'mock' | 'base' | 'sft'
  readonly service: string
  readonly status: 'ok'
}

function toSystemHealth(response: HealthResponse): SystemHealth {
  return {
    capability: response.capability,
    contractVersion: response.contract_version,
    knowledgeReleaseId: response.knowledge_release_id,
    modelVersion: response.model_version,
    persistence: response.persistence,
    provider: response.provider,
    runtimeMode: response.runtime_mode,
    service: response.service,
    status: response.status,
  }
}

export async function getSystemHealth(): Promise<SystemHealth> {
  const { data, response } = await getHealth({ client: apiClient })
  if (!data) {
    throw new ApiRequestError('后端健康检查失败。', response?.status)
  }
  return toSystemHealth(data)
}
