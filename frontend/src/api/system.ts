import { apiClient } from './client'
import { ApiRequestError } from './error'
import { getHealth } from './generated'

export async function getSystemHealth() {
  const { data, response } = await getHealth({ client: apiClient })
  if (!data) {
    throw new ApiRequestError('后端健康检查失败。', response?.status)
  }
  return data
}
