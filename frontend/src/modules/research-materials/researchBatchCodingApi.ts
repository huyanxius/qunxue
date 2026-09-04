import { getResearchBatchCoding as getResearchBatchCodingRequest, retryResearchBatchCoding as retryResearchBatchCodingRequest, startResearchBatchCoding as startResearchBatchCodingRequest } from '../../api/generated'
import { apiClient } from '../../api/client'
import type { ResearchBatchCodingRun } from './researchBatchCodingModel'

function normalize(value: any): ResearchBatchCodingRun {
  return {
    runId: value.run_id, taskId: value.task_id, materialId: value.material_id,
    parseId: value.parse_id, parseVersion: value.parse_version, status: value.status,
    totalSegments: value.total_segments, processedSegments: value.processed_segments,
    annotationIds: value.annotation_ids, codeIds: value.code_ids,
    lowConfidenceSegments: value.low_confidence_segments, errorCode: value.error_code,
    retryCount: value.retry_count,
  }
}

function key(prefix: string) {
  return `${prefix}:${globalThis.crypto?.randomUUID?.() ?? Date.now()}`
}

export async function startResearchBatchCoding(taskId: string, materialId: string): Promise<ResearchBatchCodingRun> {
  const result = await startResearchBatchCodingRequest({ client: apiClient, path: { task_id: taskId }, query: { material_id: materialId }, headers: { 'Idempotency-Key': key('batch') } })
  if (!result.data) throw new Error('批量编码启动失败。')
  return normalize(result.data)
}

export async function getResearchBatchCodingRun(taskId: string, runId: string): Promise<ResearchBatchCodingRun> {
  const result = await getResearchBatchCodingRequest({ client: apiClient, path: { task_id: taskId, run_id: runId } })
  if (!result.data) throw new Error('批量编码进度暂时无法读取。')
  return normalize(result.data)
}

export async function retryResearchBatchCodingRun(taskId: string, runId: string): Promise<ResearchBatchCodingRun> {
  const result = await retryResearchBatchCodingRequest({ client: apiClient, path: { task_id: taskId, run_id: runId }, headers: { 'Idempotency-Key': key('batch-retry') } })
  if (!result.data) throw new Error('批量编码重试失败。')
  return normalize(result.data)
}
