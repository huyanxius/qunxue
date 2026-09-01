import { apiClient } from '../../api/client'
import {
  createCorrectedTranscriptVersion as createCorrectedTranscriptVersionRequest,
  getMaterialTranscription as getMaterialTranscriptionRequest,
  importMaterialTranscript as importMaterialTranscriptRequest,
  startMaterialTranscription as startMaterialTranscriptionRequest,
} from '../../api/generated'
import {
  normalizeTranscriptionWorkspace,
  normalizeTranscriptVersion,
  type TranscriptSegment,
  type TranscriptVersion,
  type TranscriptionWorkspace,
} from './transcriptionModel'

function idempotencyKey(prefix: string) {
  return globalThis.crypto?.randomUUID?.()
    ?? `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`
}

function requireData<T>(result: { data?: T; error?: unknown }, fallback: string): T {
  if (result.error !== undefined && result.error !== null) {
    const error = result.error as { error?: { message?: string }; detail?: string }
    throw new Error(error.error?.message || error.detail || fallback)
  }
  if (result.data === undefined || result.data === null) throw new Error(fallback)
  return result.data
}

export function mediaContentUrl(taskId: string, materialId: string): string {
  return `/api/research-tasks/${encodeURIComponent(taskId)}/materials/${encodeURIComponent(materialId)}/content`
}

export async function getTranscriptionWorkspace(
  taskId: string,
  materialId: string,
  signal?: AbortSignal,
): Promise<TranscriptionWorkspace> {
  const result = await getMaterialTranscriptionRequest({
    client: apiClient,
    path: { task_id: taskId, material_id: materialId },
    signal,
  })
  return normalizeTranscriptionWorkspace(requireData(result, '转录时间轴暂时无法加载。'))
}

export async function importTranscript(
  taskId: string,
  materialId: string,
  file: File,
): Promise<TranscriptVersion> {
  const result = await importMaterialTranscriptRequest({
    client: apiClient,
    path: { task_id: taskId, material_id: materialId },
    headers: { 'Idempotency-Key': idempotencyKey('transcript-import') },
    body: { file },
  })
  return normalizeTranscriptVersion(requireData(result, '转录稿导入失败。'))
}

export async function createCorrectedTranscriptVersion(
  taskId: string,
  materialId: string,
  baseVersionId: string,
  segments: TranscriptSegment[],
): Promise<TranscriptVersion> {
  const result = await createCorrectedTranscriptVersionRequest({
    client: apiClient,
    path: { task_id: taskId, material_id: materialId },
    headers: { 'Idempotency-Key': idempotencyKey('transcript-correction') },
    body: {
      base_version_id: baseVersionId,
      segments: segments.map((item) => ({
        segment_id: item.segmentId,
        ordinal: item.ordinal,
        speaker: item.speaker,
        start_ms: item.startMs,
        end_ms: item.endMs,
        text: item.text,
      })),
    },
  })
  return normalizeTranscriptVersion(requireData(result, '转录校订保存失败。'))
}

export async function startAutomaticTranscription(
  taskId: string,
  materialId: string,
): Promise<TranscriptVersion> {
  const result = await startMaterialTranscriptionRequest({
    client: apiClient,
    path: { task_id: taskId, material_id: materialId },
    headers: { 'Idempotency-Key': idempotencyKey('transcription-run') },
  })
  return normalizeTranscriptVersion(requireData(result, '自动转写启动失败。'))
}
