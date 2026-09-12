import { apiClient } from './client'
import { getRoadshowSettings as get, saveRoadshowSettings as save, resetRoadshowSettings as reset } from './generated'
export interface RoadshowCase {
  title: string
  keywords: string[]
  question: string
  options: string[]
  steps: string[]
  knowledge_queries?: string[]
  web_queries?: string[]
  answer: string
}
export interface RoadshowSettings {
  enabled?: boolean
  canvas_enabled?: boolean
  active_case?: number
  chunk_delay?: number
  cases: RoadshowCase[]
}
export const getRoadshowSettings = () => get({ client: apiClient })
export const saveRoadshowSettings = (body: RoadshowSettings) => save({ client: apiClient, body, throwOnError: true })
export const resetRoadshowSettings = () => reset({ client: apiClient, throwOnError: true })
