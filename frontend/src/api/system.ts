import { apiClient } from './client'
import { ApiRequestError } from './error'
import { getHealth, type HealthResponse } from './generated'

export interface SystemHealth {
  readonly contractVersion: string
  readonly persistence: 'sqlite'
  readonly runtimeMode: 'inline_demo'
  readonly service: string
  readonly status: 'ok'
}

function toSystemHealth(response: HealthResponse): SystemHealth {
  return {
    contractVersion: response.contract_version,
    persistence: response.persistence,
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
