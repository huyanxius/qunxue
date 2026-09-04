import {
  getResearchBatchCodingRun as getResearchBatchCodingRunFromApi,
  retryResearchBatchCodingRun as retryResearchBatchCodingRunFromApi,
  startResearchBatchCoding as startResearchBatchCodingFromApi,
} from './researchBatchCodingApi'
import type { ResearchBatchCodingRun } from './researchBatchCodingModel'

export type { ResearchBatchCodingRun } from './researchBatchCodingModel'

/** Public module facade keeps app routes independent of the transport adapter. */
export function startResearchBatchCoding(taskId: string, materialId: string): Promise<ResearchBatchCodingRun> {
  return startResearchBatchCodingFromApi(taskId, materialId)
}

export function getResearchBatchCodingRun(taskId: string, runId: string): Promise<ResearchBatchCodingRun> {
  return getResearchBatchCodingRunFromApi(taskId, runId)
}

export function retryResearchBatchCodingRun(taskId: string, runId: string): Promise<ResearchBatchCodingRun> {
  return retryResearchBatchCodingRunFromApi(taskId, runId)
}
