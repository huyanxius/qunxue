import { apiClient } from '../../api/client'
import { createMultipartBody } from '../../api/multipart'
import {
  exportResearchProjectArchive,
  listResearchProjectAuditEvents,
  previewResearchProjectQdpxImport,
} from '../../api/generated'

type GeneratedResult<T> = {
  data?: T
  error?: unknown
  response?: Response
}

export type ResearchAuditEvent = {
  event_id: string
  event_type: string
  object_type: string
  object_id: string
  object_version: string | null
  actor_type: string
  actor_id: string | null
  payload: Record<string, unknown>
  occurred_at: string
}

export type QdpxImportPreview = {
  exchange_id: string
  valid?: true
  validation_scope?: 'official-xsd'
  specification_version?: '1.0'
  project: {
    name: string
    origin: string
    source_count: number
    code_count: number
    memo_count: number
    case_count: number
  }
  restored?: false
}

export type ResearchArchiveDownload = {
  blob: Blob
  filename: string
  exchangeId: string
  sha256: string
  lossCount: number
  blockingLossCount: number
}

function exchangeKey() {
  return `research-exchange:${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}:${Math.random()}`}`
}

function errorMessage(error: unknown) {
  const envelope = error && typeof error === 'object' ? error as Record<string, unknown> : {}
  const detail = envelope.error && typeof envelope.error === 'object'
    ? envelope.error as Record<string, unknown>
    : {}
  return typeof detail.message === 'string' ? detail.message : '研究项目交换请求失败。'
}

function unwrap<T>(result: GeneratedResult<T>): T {
  if (result.error) throw new Error(errorMessage(result.error))
  if (result.data === undefined) throw new Error('研究项目交换请求没有返回结果。')
  return result.data
}

function filenameFromDisposition(value: string | null) {
  const encoded = value?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (!encoded) return 'research-project.zip'
  try {
    return decodeURIComponent(encoded)
  } catch {
    return 'research-project.zip'
  }
}

function countHeader(response: Response, name: string) {
  const value = Number(response.headers.get(name))
  return Number.isFinite(value) && value >= 0 ? value : 0
}

export async function listResearchAuditEvents(
  taskId: string,
  signal?: AbortSignal,
): Promise<ResearchAuditEvent[]> {
  const result = await listResearchProjectAuditEvents({
    client: apiClient,
    path: { task_id: taskId },
    signal,
  })
  return unwrap(result).items
}

export async function exportResearchArchive(taskId: string): Promise<ResearchArchiveDownload> {
  const result = await exportResearchProjectArchive({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': exchangeKey() },
  })
  const blob = unwrap(result)
  const response = result.response
  if (!response) throw new Error('研究归档响应缺少下载元数据。')
  return {
    blob,
    filename: filenameFromDisposition(response.headers.get('Content-Disposition')),
    exchangeId: response.headers.get('X-Qunxue-Exchange-Id') ?? '',
    sha256: response.headers.get('X-Qunxue-Artifact-SHA256') ?? '',
    lossCount: countHeader(response, 'X-Qunxue-Exchange-Loss-Count'),
    blockingLossCount: countHeader(
      response,
      'X-Qunxue-Exchange-Blocking-Loss-Count',
    ),
  }
}

export async function previewQdpxImport(
  taskId: string,
  file: File,
): Promise<QdpxImportPreview> {
  const multipart = await createMultipartBody([{ name: 'file', file }])
  const result = await previewResearchProjectQdpxImport({
    client: apiClient,
    path: { task_id: taskId },
    headers: {
      'Content-Type': multipart.contentType,
      'Idempotency-Key': exchangeKey(),
    },
    body: { file },
    bodySerializer: () => multipart.body,
  })
  return unwrap(result)
}
