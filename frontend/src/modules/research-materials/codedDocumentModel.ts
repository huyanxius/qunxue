import type { AnalysisAnnotation, AnalysisRecordStatus } from './researchAnalysisModel'

export type CodedAnnotation = {
  readonly annotation: AnalysisAnnotation
  readonly label: string
  readonly status: AnalysisRecordStatus
}

export type CodedTextRun = {
  readonly text: string
  readonly annotationIds: string[]
  readonly statuses: AnalysisRecordStatus[]
}

type ResolvedRange = {
  readonly annotationId: string
  readonly start: number
  readonly end: number
  readonly status: AnalysisRecordStatus
}

const STATUS_ORDER: AnalysisRecordStatus[] = ['candidate', 'confirmed', 'rejected']

function clamp(value: number, lower: number, upper: number): number {
  return Math.min(upper, Math.max(lower, Number.isFinite(value) ? value : lower))
}

/**
 * Offset data is persisted against a parse version and can legitimately drift when a
 * parser normalises whitespace. Prefer the quoted evidence when it no longer matches
 * the stored offsets; this keeps the visual mark attached to the words a researcher
 * actually selected instead of silently highlighting a neighbouring sentence.
 */
function resolveRange(text: string, item: CodedAnnotation): ResolvedRange | null {
  if (!text) return null
  const annotation = item.annotation
  const rawStart = clamp(annotation.quote_start, 0, text.length)
  const rawEnd = clamp(annotation.quote_end, rawStart, text.length)
  if (rawEnd > rawStart && (!annotation.quote || text.slice(rawStart, rawEnd) === annotation.quote)) {
    return { annotationId: annotation.annotation_id, start: rawStart, end: rawEnd, status: item.status }
  }
  if (annotation.quote?.trim()) {
    const quote = annotation.quote
    let found = text.indexOf(quote)
    if (found >= 0 && rawStart > 0) {
      // If the same wording appears more than once, choose the occurrence nearest to
      // the persisted offset rather than always jumping to the first occurrence.
      let cursor = found
      let nearest = found
      while (cursor >= 0) {
        if (Math.abs(cursor - rawStart) < Math.abs(nearest - rawStart)) nearest = cursor
        cursor = text.indexOf(quote, cursor + 1)
      }
      found = nearest
    }
    if (found >= 0) return { annotationId: annotation.annotation_id, start: found, end: found + quote.length, status: item.status }
  }
  return rawEnd > rawStart
    ? { annotationId: annotation.annotation_id, start: rawStart, end: rawEnd, status: item.status }
    : null
}

export function buildCodedTextRuns(text: string, items: readonly CodedAnnotation[]): CodedTextRun[] {
  if (!text) return []
  const ranges = items
    .map((item) => resolveRange(text, item))
    .filter((range): range is ResolvedRange => Boolean(range))
  if (!ranges.length) return [{ text, annotationIds: [], statuses: [] }]

  const boundaries = Array.from(new Set([0, text.length, ...ranges.flatMap((range) => [range.start, range.end])]))
    .sort((left, right) => left - right)
  const runs: CodedTextRun[] = []
  for (let index = 0; index < boundaries.length - 1; index += 1) {
    const start = boundaries[index]
    const end = boundaries[index + 1]
    if (end <= start) continue
    const covering = ranges
      .filter((range) => range.start < end && range.end > start)
      .sort((left, right) => left.start - right.start || left.end - right.end || left.annotationId.localeCompare(right.annotationId))
    const statuses = Array.from(new Set(covering.map((range) => range.status)))
      .sort((left, right) => STATUS_ORDER.indexOf(left) - STATUS_ORDER.indexOf(right))
    runs.push({
      text: text.slice(start, end),
      annotationIds: covering.map((range) => range.annotationId),
      statuses,
    })
  }
  return runs
}

export function codeColor(index: number): string {
  const palette = ['#3f6f8f', '#8e5a78', '#5f7d4b', '#a27635', '#725d8f', '#4b817c', '#9a5c48']
  return palette[Math.abs(index) % palette.length]
}
