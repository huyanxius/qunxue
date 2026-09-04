import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CodedDocumentWorkbench } from './CodedDocumentWorkbench'
import type { AnalysisAnnotation, AnalysisCode } from './researchAnalysisModel'
import type { ResearchMaterial, ResearchMaterialSegment } from './researchMaterialsModel'

afterEach(() => cleanup())

const material: ResearchMaterial = {
  materialId: 'material-1',
  taskId: 'task-1',
  filename: '访谈-01.txt',
  mediaType: 'text/plain',
  sizeBytes: 120,
  status: 'ready',
  version: 1,
  parseVersion: 1,
  segmentCount: 1,
  updatedAt: '2026-09-04T00:00:00Z',
  errorCode: null,
  materialKind: 'interview_transcript',
}

const segment: ResearchMaterialSegment = {
  segmentId: 'segment-1',
  materialId: 'material-1',
  parseId: 'parse-1',
  ordinal: 0,
  kind: 'paragraph',
  text: '家庭成员重新分配了照护责任。',
  locator: {
    blockIndex: null,
    charEnd: 15,
    charStart: 0,
    headingPath: ['访谈'],
    lineEnd: 1,
    lineStart: 1,
    page: null,
    paragraph: 1,
  },
}

const annotation: AnalysisAnnotation = {
  annotation_id: 'annotation-1',
  annotation_kind: 'descriptive',
  case_label: null,
  created_at: '2026-09-04T00:00:00Z',
  locator: { block_index: null, char_end: 15, char_start: 0, line_end: 1, line_start: 1, page: null, paragraph: 1, section_path: ['访谈'] },
  material_id: 'material-1',
  note: '责任发生变化',
  observed_at: null,
  parse_id: 'parse-1',
  quote: '重新分配了照护责任',
  quote_end: 12,
  quote_hash: 'a'.repeat(64),
  quote_start: 4,
  reflection: null,
  segment_content_hash: 'b'.repeat(64),
  segment_id: 'segment-1',
  source_available: true,
  task_id: 'task-1',
  unavailable_reason: null,
}

const code: AnalysisCode = {
  agent_run_id: null,
  agent_turn_id: null,
  annotation_ids: ['annotation-1'],
  code_id: 'code-1',
  conversation_id: null,
  created_at: '2026-09-04T00:00:00Z',
  decided_at: null,
  decision_reason: null,
  definition: '责任安排发生变化',
  label: '照护责任重组',
  rationale: '原文明确描述重新分配',
  source: 'researcher',
  status: 'confirmed',
  task_id: 'task-1',
  tool_call_id: null,
  version: 1,
}

function renderReader() {
  return render(
    <CodedDocumentWorkbench
      material={material}
      segments={[segment]}
      allSegments={[segment]}
      totalSegmentCount={1}
      headings={[]}
      selectedSegmentId={null}
      detailLoading={false}
      note={null}
      outlineOpen
      searchOpen={false}
      query=""
      matchCount={1}
      page={0}
      pageCount={1}
      annotations={[annotation]}
      codes={[code]}
      registerSegment={vi.fn()}
      onBack={vi.fn()}
      onToggleOutline={vi.fn()}
      onToggleSearch={vi.fn()}
      onQueryChange={vi.fn()}
      onOpenArchive={vi.fn()}
      onSelectSegment={vi.fn()}
      onTextSelection={vi.fn()}
      onPageChange={vi.fn()}
    />
  )
}

describe('coded document workbench', () => {
  it('opens the evidence inspector from a coding stripe', () => {
    renderReader()
    fireEvent.click(screen.getByRole('button', { name: '照护责任重组 · 已确认' }))
    const inspector = screen.getByRole('complementary', { name: '编码证据检查器' })
    expect(within(inspector).getByText('重新分配了照护责任')).toBeVisible()
    expect(within(inspector).getByText('责任发生变化')).toBeVisible()
  })

  it('opens retrieved segments as a source-linked result view', () => {
    renderReader()
    fireEvent.click(screen.getByRole('button', { name: /检索/ }))
    const retrieved = screen.getByRole('complementary', { name: '检索编码片段' })
    expect(within(retrieved).getByText('检索编码片段')).toBeVisible()
    expect(within(retrieved).getByText('重新分配了照护责任')).toBeVisible()
  })
})
