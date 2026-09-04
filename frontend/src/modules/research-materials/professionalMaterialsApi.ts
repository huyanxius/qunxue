import { apiClient } from '../../api/client'
import { createMultipartBody } from '../../api/multipart'
import {
  batchUploadMaterials as batchUploadMaterialsRequest,
  createMaterialBatch as createMaterialBatchRequest,
  createMaterialCollection as createMaterialCollectionRequest,
  createMaterialRelation as createMaterialRelationRequest,
  createLiteratureEntry as createLiteratureEntryRequest,
  createResearchCase as createResearchCaseRequest,
  exportLiteratureEntries as exportLiteratureEntriesRequest,
  getProfessionalMaterialArchive as getProfessionalMaterialArchiveRequest,
  importLiteratureEntries as importLiteratureEntriesRequest,
  resolveDoiMetadata as resolveDoiMetadataRequest,
  updateProfessionalMaterialProfile as updateProfessionalMaterialProfileRequest,
} from '../../api/generated'
import type {
  BatchUploadResult,
  CreateLiteratureEntryInput,
  CreateMaterialCollectionInput,
  CreateMaterialRelationInput,
  CreateResearchCaseInput,
  DoiMetadataCandidate,
  LiteratureEntry,
  LiteratureFormat,
  MaterialBatch,
  MaterialCollection,
  MaterialKind,
  MaterialRelation,
  ProfessionalMaterialArchive,
  ProfessionalMaterialProfile,
  ProfessionalMaterialProfileUpdate,
  ResearchCase,
} from './professionalMaterialsModel'

export class ProfessionalMaterialsApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ProfessionalMaterialsApiError'
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

function requireData<T>(result: GeneratedResult<T>, fallback: string): T {
  if (result.error !== undefined && result.error !== null) {
    if (record(result.error).name === 'AbortError') throw result.error
    const raw = record(result.error)
    const nested = record(raw.error)
    const message = typeof nested.message === 'string'
      ? nested.message
      : typeof raw.message === 'string' ? raw.message : fallback
    throw new ProfessionalMaterialsApiError(message, result.response?.status ?? 0)
  }
  if (result.data === undefined || result.data === null) {
    throw new ProfessionalMaterialsApiError(fallback, result.response?.status ?? 0)
  }
  return result.data
}

function idempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `professional-material:${Date.now()}:${Math.random().toString(36).slice(2)}`
}

export async function getProfessionalMaterialArchive(
  taskId: string,
  signal?: AbortSignal,
): Promise<ProfessionalMaterialArchive> {
  const result = await getProfessionalMaterialArchiveRequest({
    client: apiClient, path: { task_id: taskId }, signal,
  })
  return requireData(result, '研究档案暂时无法加载。')
}

export async function updateProfessionalMaterialProfile(
  taskId: string,
  materialId: string,
  body: ProfessionalMaterialProfileUpdate,
): Promise<ProfessionalMaterialProfile> {
  const result = await updateProfessionalMaterialProfileRequest({
    client: apiClient,
    headers: { 'Idempotency-Key': idempotencyKey() },
    path: { task_id: taskId, material_id: materialId },
    body,
  })
  return requireData(result, '材料档案暂时无法保存。')
}

export async function createMaterialBatch(
  taskId: string,
  name: string,
): Promise<MaterialBatch> {
  const result = await createMaterialBatchRequest({
    client: apiClient,
    headers: { 'Idempotency-Key': idempotencyKey() },
    path: { task_id: taskId },
    body: { name },
  })
  return requireData(result, '批次暂时无法创建。')
}

export async function createMaterialCollection(
  taskId: string,
  body: CreateMaterialCollectionInput,
): Promise<MaterialCollection> {
  const result = await createMaterialCollectionRequest({
    client: apiClient,
    headers: { 'Idempotency-Key': idempotencyKey() },
    path: { task_id: taskId },
    body,
  })
  return requireData(result, '集合暂时无法创建。')
}

export async function createResearchCase(
  taskId: string,
  body: CreateResearchCaseInput,
): Promise<ResearchCase> {
  const result = await createResearchCaseRequest({
    client: apiClient,
    headers: { 'Idempotency-Key': idempotencyKey() },
    path: { task_id: taskId },
    body,
  })
  return requireData(result, '个案暂时无法创建。')
}

export async function createMaterialRelation(
  taskId: string,
  body: CreateMaterialRelationInput,
): Promise<MaterialRelation> {
  const result = await createMaterialRelationRequest({
    client: apiClient,
    headers: { 'Idempotency-Key': idempotencyKey() },
    path: { task_id: taskId },
    body,
  })
  return requireData(result, '材料关系暂时无法创建。')
}

export async function createLiteratureEntry(
  taskId: string,
  body: CreateLiteratureEntryInput,
): Promise<LiteratureEntry> {
  const result = await createLiteratureEntryRequest({
    client: apiClient,
    headers: { 'Idempotency-Key': idempotencyKey() },
    path: { task_id: taskId },
    body,
  })
  return requireData(result, '文献条目暂时无法创建。')
}

export async function uploadMaterialBatch(
  taskId: string,
  batchId: string,
  files: File[],
  materialKind: MaterialKind,
): Promise<BatchUploadResult> {
  const multipart = await createMultipartBody([
    ...files.map((file) => ({ name: 'files', file }) as const),
    { name: 'material_kind', value: materialKind },
  ])
  const result = await batchUploadMaterialsRequest({
    client: apiClient,
    headers: {
      'Content-Type': multipart.contentType,
      'Idempotency-Key': idempotencyKey(),
    },
    path: { task_id: taskId, batch_id: batchId },
    body: { files, material_kind: materialKind },
    bodySerializer: () => multipart.body,
  })
  return requireData(result, '批量上传暂时无法完成。')
}

export async function importLiteratureEntries(
  taskId: string,
  file: File,
  exchangeFormat: LiteratureFormat,
): Promise<LiteratureEntry[]> {
  const result = await importLiteratureEntriesRequest({
    client: apiClient,
    headers: { 'Idempotency-Key': idempotencyKey() },
    path: { task_id: taskId },
    body: { file, exchange_format: exchangeFormat },
  })
  return requireData(result, '文献条目暂时无法导入。')
}

export async function resolveDoiMetadata(
  taskId: string,
  doi: string,
): Promise<DoiMetadataCandidate> {
  const result = await resolveDoiMetadataRequest({
    client: apiClient,
    path: { task_id: taskId },
    query: { doi },
  })
  return requireData(result, 'DOI 元数据暂时无法获取。')
}

export async function exportLiteratureEntries(
  taskId: string,
  exchangeFormat: LiteratureFormat,
): Promise<Blob> {
  const result = await exportLiteratureEntriesRequest({
    client: apiClient,
    path: { task_id: taskId },
    query: { exchange_format: exchangeFormat },
  })
  if (result.error !== undefined && result.error !== null) {
    requireData(result as GeneratedResult<never>, '文献条目暂时无法导出。')
  }
  const data = result.data
  if (data instanceof Blob) return data
  const contentType = exchangeFormat === 'csl_json' ? 'application/json' : 'text/plain'
  return new Blob([
    typeof data === 'string' ? data : JSON.stringify(data ?? []),
  ], { type: contentType })
}
