/**
 * Frontend contract for the task-scoped research-material corpus.
 * Transport fields intentionally mirror the API so a generated client can be
 * swapped in without changing the research workspace components.
 */

export const RESEARCH_MATERIAL_ACCEPT = '.pdf,.docx,.txt,.md,.markdown,.mp3,.m4a,.wav,.mp4,.webm,application/pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,audio/mpeg,audio/mp4,audio/x-m4a,audio/wav,audio/x-wav,video/mp4,video/webm'

export const RESEARCH_MATERIAL_MEDIA_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
  'audio/mpeg',
  'audio/mp4',
  'audio/x-m4a',
  'audio/wav',
  'audio/x-wav',
  'video/mp4',
  'video/webm',
] as const

export type ResearchMaterialMediaType = typeof RESEARCH_MATERIAL_MEDIA_TYPES[number]
export type ResearchMaterialKind = 'paper' | 'interview_transcript' | 'observation_record' | 'field_note' | 'other'
export type ResearchMaterialStatus = 'uploaded' | 'processing' | 'ready' | 'failed' | 'deleted'
export type ResearchMaterialIngestionStatus = 'queued' | 'processing' | 'ready' | 'failed'

export type ResearchMaterialLocator = {
  page: number | null
  headingPath: string[]
  paragraph: number | null
  lineStart: number | null
  lineEnd: number | null
  charStart: number | null
  charEnd: number | null
  blockIndex?: number | null
  blockId?: string | null
  timeStartMs?: number | null
  timeEndMs?: number | null
  speaker?: string | null
}

export type ResearchMaterialSegment = {
  segmentId: string
  materialId: string
  parseId: string
  ordinal: number
  kind: string
  text: string
  locator: ResearchMaterialLocator
}

export type ResearchMaterial = {
  materialId: string
  taskId: string
  filename: string
  mediaType: string
  sizeBytes: number
  status: ResearchMaterialStatus
  version: number
  parseVersion: number | null
  segmentCount: number
  updatedAt: string
  errorCode: string | null
  ingestionJobId?: string | null
  ingestionStatus?: ResearchMaterialIngestionStatus
  unavailableReason?: string | null
  materialKind?: ResearchMaterialKind | null
  segments?: ResearchMaterialSegment[]
}

export type ResearchMaterialList = {
  taskId: string
  items: ResearchMaterial[]
}

export type ResearchMaterialSearchHit = {
  materialId: string
  parseId: string
  segmentId: string
  title: string
  materialKind: ResearchMaterialKind
  materialFormat: string
  excerpt: string
  locator: ResearchMaterialLocator
  score: number
}

export type ResearchMaterialSearchResult = {
  taskId: string
  query: string
  total: number
  items: ResearchMaterialSearchHit[]
}

type RawRecord = Record<string, unknown>

function record(value: unknown): RawRecord {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as RawRecord
    : {}
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function nullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function normalizeStatus(value: unknown): ResearchMaterialStatus {
  if (value === 'uploaded' || value === 'ready' || value === 'failed' || value === 'deleted') return value
  return 'processing'
}

function normalizeKind(value: unknown): ResearchMaterialKind | null {
  if (value === 'observation') return 'observation_record'
  return value === 'paper' || value === 'interview_transcript' || value === 'observation_record' || value === 'field_note' || value === 'other'
    ? value
    : null
}

function normalizeIngestionStatus(
  value: unknown,
  materialStatus: ResearchMaterialStatus,
): ResearchMaterialIngestionStatus {
  if (value === 'queued' || value === 'processing' || value === 'ready' || value === 'failed') return value
  if (materialStatus === 'ready') return 'ready'
  if (materialStatus === 'failed') return 'failed'
  return 'processing'
}

/** Normalize server locators while preserving only positions the parser supplied. */
export function normalizeMaterialLocator(value: unknown): ResearchMaterialLocator {
  const raw = record(value)
  const rawHeadingPath = raw.section_path ?? raw.heading_path ?? raw.headingPath
  const headingPath = Array.isArray(rawHeadingPath)
    ? rawHeadingPath.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      : []
  const locator: ResearchMaterialLocator = {
    page: nullableNumber(raw.page),
    headingPath,
    paragraph: nullableNumber(raw.paragraph),
    lineStart: nullableNumber(raw.line_start ?? raw.lineStart),
    lineEnd: nullableNumber(raw.line_end ?? raw.lineEnd),
    charStart: nullableNumber(raw.char_start ?? raw.charStart),
    charEnd: nullableNumber(raw.char_end ?? raw.charEnd),
  }
  const blockIndex = nullableNumber(raw.block_index ?? raw.blockIndex)
  const blockId = nullableString(raw.block_id ?? raw.blockId)
  const timeStartMs = nullableNumber(raw.time_start_ms ?? raw.timeStartMs)
  const timeEndMs = nullableNumber(raw.time_end_ms ?? raw.timeEndMs)
  const speaker = nullableString(raw.speaker)
  if (blockIndex !== null) locator.blockIndex = blockIndex
  if (blockId !== null) locator.blockId = blockId
  if (timeStartMs !== null) locator.timeStartMs = timeStartMs
  if (timeEndMs !== null) locator.timeEndMs = timeEndMs
  if (speaker !== null) locator.speaker = speaker
  return locator
}

function normalizeSegment(value: unknown, materialId: string, index: number): ResearchMaterialSegment {
  const raw = record(value)
  return {
    segmentId: stringValue(raw.segment_id ?? raw.segmentId, `${materialId}:segment:${index + 1}`),
    materialId: stringValue(raw.material_id ?? raw.materialId, materialId),
    parseId: stringValue(raw.parse_id ?? raw.parseId),
    ordinal: numberValue(raw.ordinal, index),
    kind: stringValue(raw.kind, 'paragraph'),
    text: stringValue(raw.text ?? raw.excerpt),
    locator: normalizeMaterialLocator(raw.locator),
  }
}

/** Normalize one generated segment response without inventing source text. */
export function normalizeResearchMaterialSegment(
  value: unknown,
  fallbackMaterialId = '',
): ResearchMaterialSegment {
  const raw = record(value)
  const materialId = stringValue(raw.material_id ?? raw.materialId, fallbackMaterialId)
  return normalizeSegment(raw, materialId, 0)
}

export function normalizeResearchMaterial(value: unknown): ResearchMaterial {
  const raw = record(value)
  const materialId = stringValue(raw.material_id ?? raw.materialId)
  const status = normalizeStatus(raw.status)
  const segments = Array.isArray(raw.segments)
    ? raw.segments.map((item, index) => normalizeSegment(item, materialId, index))
    : undefined
  return {
    materialId,
    taskId: stringValue(raw.task_id ?? raw.taskId),
    filename: stringValue(raw.filename ?? raw.original_filename ?? raw.originalFilename, '未命名材料'),
    mediaType: stringValue(raw.media_type ?? raw.mediaType),
    sizeBytes: numberValue(raw.size_bytes ?? raw.sizeBytes),
    status,
    version: numberValue(raw.version, 1),
    parseVersion: nullableNumber(raw.parse_version ?? raw.parseVersion),
    segmentCount: numberValue(raw.segment_count ?? raw.segmentCount, segments?.length ?? 0),
    updatedAt: stringValue(raw.updated_at ?? raw.updatedAt),
    errorCode: nullableString(raw.error_code ?? raw.errorCode),
    ingestionJobId: nullableString(raw.ingestion_job_id ?? raw.ingestionJobId),
    ingestionStatus: normalizeIngestionStatus(raw.ingestion_status ?? raw.ingestionStatus, status),
    unavailableReason: nullableString(raw.unavailable_reason ?? raw.unavailableReason),
    materialKind: normalizeKind(raw.material_kind ?? raw.materialKind),
    segments,
  }
}

export function normalizeResearchMaterialList(value: unknown, fallbackTaskId: string): ResearchMaterialList {
  const raw = record(value)
  const items = Array.isArray(raw.items)
    ? raw.items.map(normalizeResearchMaterial)
    : Array.isArray(value)
      ? value.map(normalizeResearchMaterial)
      : []
  return {
    taskId: stringValue(raw.task_id ?? raw.taskId, fallbackTaskId),
    items,
  }
}

export function normalizeResearchMaterialSearchResult(
  value: unknown,
  fallbackTaskId: string,
): ResearchMaterialSearchResult {
  const raw = record(value)
  const items = Array.isArray(raw.items) ? raw.items.map((value) => {
    const item = record(value)
    return {
      materialId: stringValue(item.material_id ?? item.materialId),
      parseId: stringValue(item.parse_id ?? item.parseId),
      segmentId: stringValue(item.segment_id ?? item.segmentId),
      title: stringValue(item.title, '未命名材料'),
      materialKind: normalizeKind(item.material_kind ?? item.materialKind) ?? 'other',
      materialFormat: stringValue(item.material_format ?? item.materialFormat),
      excerpt: stringValue(item.excerpt),
      locator: normalizeMaterialLocator(item.locator),
      score: numberValue(item.score),
    }
  }) : []
  return {
    taskId: stringValue(raw.task_id ?? raw.taskId, fallbackTaskId),
    query: stringValue(raw.query),
    total: numberValue(raw.total, items.length),
    items,
  }
}

function fileName(file: Pick<File, 'name'>): string {
  return file.name.toLowerCase()
}

export function isSupportedResearchMaterialFile(file: Pick<File, 'name' | 'type'>): boolean {
  const name = fileName(file)
  const extension = ['.pdf', '.docx', '.txt', '.md', '.markdown', '.mp3', '.m4a', '.wav', '.mp4', '.webm']
    .find((candidate) => name.endsWith(candidate))
  if (!extension) return false

  // Browsers commonly report no type (or octet-stream) for local documents.
  // The server resolves those values from the extension, so rejecting them in
  // the picker would make valid user files impossible to add.
  const mediaType = file.type.split(';', 1)[0].trim().toLowerCase()
  if (!mediaType || mediaType === 'application/octet-stream') return true
  if (mediaType.startsWith('image/')) return false

  const expected: Record<string, readonly string[]> = {
    '.pdf': ['application/pdf'],
    '.docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
    '.txt': ['text/plain'],
    '.md': ['text/markdown', 'text/x-markdown', 'application/markdown', 'text/plain'],
    '.markdown': ['text/markdown', 'text/x-markdown', 'application/markdown', 'text/plain'],
    '.mp3': ['audio/mpeg', 'audio/mp3'],
    '.m4a': ['audio/mp4', 'audio/x-m4a'],
    '.wav': ['audio/wav', 'audio/x-wav', 'audio/vnd.wave'],
    '.mp4': ['video/mp4'],
    '.webm': ['video/webm'],
  }
  return expected[extension]?.includes(mediaType) ?? false
}

export function materialKindLabel(kind: ResearchMaterialKind): string {
  return {
    paper: '论文',
    interview_transcript: '访谈转录',
    observation_record: '观察记录',
    field_note: '田野笔记',
    other: '其他',
  }[kind]
}

export function materialStatusLabel(status: ResearchMaterialStatus): string {
  return {
    uploaded: '原件已保存',
    processing: '正在解析',
    ready: '可检索',
    failed: '解析失败',
    deleted: '已删除',
  }[status]
}

export function materialMediaLabel(mediaType: string, filename = ''): string {
  const lowerName = filename.toLowerCase()
  if (mediaType === 'audio/mpeg' || lowerName.endsWith('.mp3')) return 'MP3'
  if (mediaType === 'audio/mp4' || mediaType === 'audio/x-m4a' || lowerName.endsWith('.m4a')) return 'M4A'
  if (mediaType === 'audio/wav' || mediaType === 'audio/x-wav' || lowerName.endsWith('.wav')) return 'WAV'
  if (mediaType === 'video/mp4' || lowerName.endsWith('.mp4')) return 'MP4'
  if (mediaType === 'video/webm' || lowerName.endsWith('.webm')) return 'WebM'
  if (mediaType === 'application/pdf' || filename.toLowerCase().endsWith('.pdf')) return 'PDF'
  if (mediaType.includes('wordprocessingml') || filename.toLowerCase().endsWith('.docx')) return 'DOCX'
  if (mediaType === 'text/markdown' || /\.(md|markdown)$/i.test(filename)) return 'Markdown'
  return 'TXT'
}

export function formatMaterialSize(sizeBytes: number): string {
  if (sizeBytes < 1024) return `${sizeBytes} B`
  if (sizeBytes < 1024 * 1024) return `${Math.round(sizeBytes / 1024)} KB`
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatMaterialLocator(locator: ResearchMaterialLocator): string {
  const parts: string[] = []
  if (locator.timeStartMs !== undefined && locator.timeStartMs !== null) {
    const start = formatMediaTime(locator.timeStartMs)
    const end = locator.timeEndMs !== undefined && locator.timeEndMs !== null
      ? formatMediaTime(locator.timeEndMs)
      : null
    parts.push(end ? `${start}–${end}` : start)
  }
  if (locator.speaker) parts.push(locator.speaker)
  if (locator.page !== null) parts.push(`第 ${locator.page} 页`)
  if (locator.headingPath.length) parts.push(locator.headingPath.join(' / '))
  if (locator.paragraph !== null) parts.push(`第 ${locator.paragraph} 段`)
  if (locator.lineStart !== null) {
    parts.push(locator.lineEnd !== null && locator.lineEnd !== locator.lineStart
      ? `第 ${locator.lineStart}–${locator.lineEnd} 行`
      : `第 ${locator.lineStart} 行`)
  }
  if (locator.charStart !== null) {
    parts.push(locator.charEnd !== null ? `字符 ${locator.charStart}–${locator.charEnd}` : `字符 ${locator.charStart}`)
  }
  return parts.join(' · ') || '原文位置未提供'
}

function formatMediaTime(milliseconds: number): string {
  const totalSeconds = Math.floor(milliseconds / 1_000)
  const hours = Math.floor(totalSeconds / 3_600)
  const minutes = Math.floor((totalSeconds % 3_600) / 60)
  const seconds = totalSeconds % 60
  const millis = milliseconds % 1_000
  const base = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`
  return hours ? `${String(hours).padStart(2, '0')}:${base}` : base
}

export function isMediaResearchMaterial(material: Pick<ResearchMaterial, 'mediaType' | 'filename'>): boolean {
  return material.mediaType.startsWith('audio/')
    || material.mediaType.startsWith('video/')
    || /\.(mp3|m4a|wav|mp4|webm)$/i.test(material.filename)
}
