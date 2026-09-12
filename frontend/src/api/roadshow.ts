import { apiClient } from './client'
import { getRoadshowSettings as get, saveRoadshowSettings as save, resetRoadshowSettings as reset } from './generated'
import type { RoadshowSettings } from './generated'
export type { RoadshowCase, RoadshowSettings } from './generated'
export const getRoadshowSettings = () => get({ client: apiClient })
export const saveRoadshowSettings = (body: RoadshowSettings) => save({ client: apiClient, body, throwOnError: true })
export const resetRoadshowSettings = () => reset({ client: apiClient, throwOnError: true })
