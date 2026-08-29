import { describe, expect, it } from 'vitest'

import {
  isSupportedResearchMaterialFile,
  materialKindLabel,
  materialStatusLabel,
  normalizeMaterialLocator,
  normalizeResearchMaterial,
  type ResearchMaterialKind,
} from './researchMaterialsModel'

describe('research material model', () => {
  it('accepts research document formats and rejects images', () => {
    expect(isSupportedResearchMaterialFile(new File(['pdf'], '论文.pdf', { type: 'application/pdf' }))).toBe(true)
    expect(isSupportedResearchMaterialFile(new File(['docx'], '访谈.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))).toBe(true)
    expect(isSupportedResearchMaterialFile(new File(['text'], '记录.txt', { type: 'text/plain' }))).toBe(true)
    expect(isSupportedResearchMaterialFile(new File(['markdown'], '方法.md', { type: 'text/markdown' }))).toBe(true)
    expect(isSupportedResearchMaterialFile(new File(['image'], '照片.png', { type: 'image/png' }))).toBe(false)
  })

  it('renders a locator without inventing page numbers', () => {
    expect(normalizeMaterialLocator({ heading_path: ['访谈一', '工作经历'], line_start: 18, line_end: 23 })).toEqual({
      headingPath: ['访谈一', '工作经历'],
      lineStart: 18,
      lineEnd: 23,
      page: null,
      paragraph: null,
      charStart: null,
      charEnd: null,
    })
  })

  it('keeps the section path returned by the research-material API', () => {
    expect(normalizeMaterialLocator({ section_path: ['访谈一', '工作经历'], paragraph: 12 })).toMatchObject({
      headingPath: ['访谈一', '工作经历'],
      paragraph: 12,
      page: null,
    })
  })

  it('keeps Chinese labels for every user-selectable material kind and status', () => {
    const kinds: ResearchMaterialKind[] = ['paper', 'interview_transcript', 'observation_record', 'field_note', 'other']
    expect(kinds.map(materialKindLabel)).toEqual(['论文', '访谈转录', '观察记录', '田野笔记', '其他'])
    expect(materialStatusLabel('processing')).toBe('正在解析')
    expect(materialStatusLabel('ready')).toBe('可检索')
    expect(materialStatusLabel('failed')).toBe('解析失败')
  })

  it('normalizes the canonical observation kind and parser block locator', () => {
    const normalized = normalizeResearchMaterial({
      material_id: 'material-1',
      task_id: 'task-1',
      filename: '观察.md',
      material_kind: 'observation_record',
      status: 'ready',
      segments: [{
        segment_id: 'segment-1',
        material_id: 'material-1',
        parse_id: 'parse-1',
        ordinal: 0,
        kind: 'paragraph',
        text: '现场记录',
        locator: { section_path: ['现场'], block_index: 7 },
      }],
    })

    expect(normalized.materialKind).toBe('observation_record')
    expect(normalized.segments?.[0]?.locator).toMatchObject({
      headingPath: ['现场'],
      blockIndex: 7,
    })
  })

  it('accepts browser generic MIME values when the filename identifies a supported document', () => {
    expect(isSupportedResearchMaterialFile(new File(['markdown'], '方法.md', { type: 'text/plain' }))).toBe(true)
    expect(isSupportedResearchMaterialFile(new File(['pdf'], '论文.pdf', { type: 'application/octet-stream' }))).toBe(true)
  })
})
