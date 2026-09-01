export type TranscriptSource = 'automatic' | 'imported' | 'manual_correction'
export type TranscriptionStatus = 'not_started' | 'unavailable' | 'processing' | 'ready' | 'failed'

export type TranscriptSegment = {
  segmentId: string
  ordinal: number
  speaker: string | null
  startMs: number | null
  endMs: number | null
  text: string
}

export type TranscriptVersion = {
  versionId: string
  materialId: string
  version: number
  source: TranscriptSource
  provider: string | null
  createdFromVersionId: string | null
  createdAt: string
  isCurrent: boolean
  segments: TranscriptSegment[]
}

export type TranscriptionWorkspace = {
  materialId: string
  status: TranscriptionStatus
  automaticAvailable: boolean
  automaticProvider: string | null
  errorCode: string | null
  currentVersion: TranscriptVersion | null
  versions: TranscriptVersion[]
}

type RawRecord = Record<string, unknown>

function record(value: unknown): RawRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as RawRecord : {}
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function nullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function normalizeSegment(value: unknown, index: number): TranscriptSegment {
  const raw = record(value)
  return {
    segmentId: stringValue(raw.segment_id ?? raw.segmentId, `segment-${index + 1}`),
    ordinal: typeof raw.ordinal === 'number' ? raw.ordinal : index,
    speaker: nullableString(raw.speaker),
    startMs: nullableNumber(raw.start_ms ?? raw.startMs),
    endMs: nullableNumber(raw.end_ms ?? raw.endMs),
    text: stringValue(raw.text),
  }
}

function normalizeVersion(value: unknown): TranscriptVersion {
  const raw = record(value)
  const source = raw.source === 'automatic' || raw.source === 'manual_correction'
    ? raw.source
    : 'imported'
  return {
    versionId: stringValue(raw.version_id ?? raw.versionId),
    materialId: stringValue(raw.material_id ?? raw.materialId),
    version: typeof raw.version === 'number' ? raw.version : 1,
    source,
    provider: nullableString(raw.provider),
    createdFromVersionId: nullableString(raw.created_from_version_id ?? raw.createdFromVersionId),
    createdAt: stringValue(raw.created_at ?? raw.createdAt),
    isCurrent: raw.is_current === true || raw.isCurrent === true,
    segments: Array.isArray(raw.segments)
      ? raw.segments.map(normalizeSegment)
      : [],
  }
}

export function normalizeTranscriptionWorkspace(value: unknown): TranscriptionWorkspace {
  const raw = record(value)
  const status = ['not_started', 'unavailable', 'processing', 'ready', 'failed'].includes(String(raw.status))
    ? raw.status as TranscriptionStatus
    : 'unavailable'
  return {
    materialId: stringValue(raw.material_id ?? raw.materialId),
    status,
    automaticAvailable: raw.automatic_available === true || raw.automaticAvailable === true,
    automaticProvider: nullableString(raw.automatic_provider ?? raw.automaticProvider),
    errorCode: nullableString(raw.error_code ?? raw.errorCode),
    currentVersion: raw.current_version || raw.currentVersion
      ? normalizeVersion(raw.current_version ?? raw.currentVersion)
      : null,
    versions: Array.isArray(raw.versions) ? raw.versions.map(normalizeVersion) : [],
  }
}

export function normalizeTranscriptVersion(value: unknown): TranscriptVersion {
  return normalizeVersion(value)
}

export function formatTranscriptTime(milliseconds: number | null): string {
  if (milliseconds === null) return '--:--.---'
  const totalSeconds = Math.floor(milliseconds / 1_000)
  const hours = Math.floor(totalSeconds / 3_600)
  const minutes = Math.floor((totalSeconds % 3_600) / 60)
  const seconds = totalSeconds % 60
  const millis = milliseconds % 1_000
  const short = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`
  return hours ? `${String(hours).padStart(2, '0')}:${short}` : short
}

export function transcriptSourceLabel(source: TranscriptSource): string {
  return {
    automatic: '自动转写',
    imported: '导入转录稿',
    manual_correction: '人工校订',
  }[source]
}
