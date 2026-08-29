import { apiClient } from '../../api/client'
import {
  deleteResearchMaterial as deleteResearchMaterialRequest,
  getResearchMaterial as getResearchMaterialRequest,
  getResearchMaterialSegment as getResearchMaterialSegmentRequest,
  listResearchMaterials as listResearchMaterialsRequest,
  reparseResearchMaterial as reparseResearchMaterialRequest,
  uploadResearchMaterial as uploadResearchMaterialRequest,
} from '../../api/generated'
import {
  normalizeResearchMaterial,
  normalizeResearchMaterialList,
  normalizeResearchMaterialSegment,
  type ResearchMaterial,
  type ResearchMaterialKind,
  type ResearchMaterialList,
  type ResearchMaterialSegment,
} from './researchMaterialsModel'

/**
 * Module-facing errors keep the UI independent of generated transport shapes.
 * A zero status means the request failed before a server response existed.
 */
export class ResearchMaterialsApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ResearchMaterialsApiError'
    this.status = status
  }
}

type GeneratedResult<T> = {
  readonly data?: T
  readonly error?: unknown
  readonly response?: Response
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function errorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'string' && error.trim()) return error
  const raw = record(error)
  const nested = record(raw.error)
  const detail = raw.detail
  if (typeof nested.message === 'string' && nested.message.trim()) return nested.message
  if (typeof raw.message === 'string' && raw.message.trim()) return raw.message
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const first = record(detail[0])
    if (typeof first.msg === 'string' && first.msg.trim()) return first.msg
  }
  return fallback
}

function isAbortError(error: unknown): boolean {
  return record(error).name === 'AbortError'
}

function statusOf(result: GeneratedResult<unknown>): number {
  return result.response?.status ?? 0
}

function requireData<T>(result: GeneratedResult<T>, fallback: string): T {
  if (result.error !== undefined && result.error !== null) {
    if (isAbortError(result.error)) throw result.error
    throw new ResearchMaterialsApiError(errorMessage(result.error, fallback), statusOf(result))
  }
  if (result.data === undefined || result.data === null) {
    throw new ResearchMaterialsApiError(fallback, statusOf(result))
  }
  return result.data
}

function requireSuccess(result: GeneratedResult<unknown>, fallback: string): void {
  if (result.error !== undefined && result.error !== null) {
    if (isAbortError(result.error)) throw result.error
    throw new ResearchMaterialsApiError(errorMessage(result.error, fallback), statusOf(result))
  }
  // Generated clients normally expose an error for non-2xx responses. Keep a
  // defensive status check so custom clients cannot silently report success.
  if (result.response && !result.response.ok) {
    throw new ResearchMaterialsApiError(fallback, result.response.status)
  }
}

function idempotencyKey() {
  return globalThis.crypto?.randomUUID?.()
    ?? `research-material:${Date.now()}:${Math.random().toString(36).slice(2)}`
}

export async function listResearchMaterials(
  taskId: string,
  signal?: AbortSignal,
): Promise<ResearchMaterialList> {
  const result = await listResearchMaterialsRequest({
    client: apiClient,
    path: { task_id: taskId },
    signal,
  })
  return normalizeResearchMaterialList(requireData(result, '研究材料暂时无法加载。'), taskId)
}

export async function getResearchMaterial(
  taskId: string,
  materialId: string,
  signal?: AbortSignal,
  parseId?: string | null,
): Promise<ResearchMaterial> {
  const result = await getResearchMaterialRequest({
    client: apiClient,
    path: { task_id: taskId, material_id: materialId },
    query: parseId ? { parse_id: parseId } : undefined,
    signal,
  })
  return normalizeResearchMaterial(requireData(result, '研究材料详情暂时无法加载。'))
}

export async function getResearchMaterialSegment(
  taskId: string,
  materialId: string,
  segmentId: string,
  signal?: AbortSignal,
  parseId?: string | null,
): Promise<ResearchMaterialSegment> {
  const result = await getResearchMaterialSegmentRequest({
    client: apiClient,
    path: { task_id: taskId, material_id: materialId, segment_id: segmentId },
    query: parseId ? { parse_id: parseId } : undefined,
    signal,
  })
  return normalizeResearchMaterialSegment(
    requireData(result, '原文片段暂时无法加载。'),
    materialId,
  )
}

export async function uploadResearchMaterial(
  taskId: string,
  file: File,
  materialKind: ResearchMaterialKind,
  signal?: AbortSignal,
): Promise<ResearchMaterial> {
  const result = await uploadResearchMaterialRequest({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: { file, material_kind: materialKind },
    signal,
  })
  return normalizeResearchMaterial(requireData(result, '研究材料上传失败。'))
}

export async function reparseResearchMaterial(
  taskId: string,
  materialId: string,
  signal?: AbortSignal,
): Promise<ResearchMaterial> {
  const result = await reparseResearchMaterialRequest({
    client: apiClient,
    path: { task_id: taskId, material_id: materialId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    signal,
  })
  return normalizeResearchMaterial(requireData(result, '研究材料重新解析失败。'))
}

export async function deleteResearchMaterial(
  taskId: string,
  materialId: string,
  signal?: AbortSignal,
): Promise<void> {
  const result = await deleteResearchMaterialRequest({
    client: apiClient,
    path: { task_id: taskId, material_id: materialId },
    headers: { 'Idempotency-Key': `delete-research-material:${materialId}` },
    signal,
  })
  requireSuccess(result, '研究材料删除失败。')
}
