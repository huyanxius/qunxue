import { describe, expect, it } from 'vitest'

import type { AnalysisAnnotation } from './researchAnalysisModel'
import { buildCodedTextRuns } from './codedDocumentModel'

function annotation(id: string, start: number, end: number, quote: string | null = null): AnalysisAnnotation {
  return {
    annotation_id: id,
    annotation_kind: 'descriptive',
    case_label: null,
    created_at: '2026-09-04T00:00:00Z',
    locator: {
      block_index: null,
      char_end: end,
      char_start: start,
      line_end: null,
      line_start: null,
      page: null,
      paragraph: null,
      section_path: [],
    },
    material_id: 'material-1',
    note: '',
    observed_at: null,
    parse_id: 'parse-1',
    quote,
    quote_end: end,
    quote_hash: 'a'.repeat(64),
    quote_start: start,
    reflection: null,
    segment_content_hash: 'b'.repeat(64),
    segment_id: 'segment-1',
    source_available: true,
    task_id: 'task-1',
    unavailable_reason: null,
  }
}

describe('coded document text ranges', () => {
  it('keeps every overlapping annotation on the exact text runs', () => {
    const runs = buildCodedTextRuns('abcdefghij', [
      { annotation: annotation('a', 1, 7), status: 'confirmed', label: '制度' },
      { annotation: annotation('b', 4, 9), status: 'candidate', label: '资源' },
    ])

    expect(runs).toEqual([
      { text: 'a', annotationIds: [], statuses: [] },
      { text: 'bcd', annotationIds: ['a'], statuses: ['confirmed'] },
      { text: 'efg', annotationIds: ['a', 'b'], statuses: ['candidate', 'confirmed'] },
      { text: 'hi', annotationIds: ['b'], statuses: ['candidate'] },
      { text: 'j', annotationIds: [], statuses: [] },
    ])
  })

  it('falls back to the quoted text when persisted offsets drift', () => {
    const runs = buildCodedTextRuns('前文需要重新分配责任。', [
      { annotation: annotation('a', 0, 2, '重新分配责任'), status: 'confirmed', label: '责任' },
    ])

    expect(runs.find((run) => run.annotationIds.includes('a'))?.text).toBe('重新分配责任')
  })
})
