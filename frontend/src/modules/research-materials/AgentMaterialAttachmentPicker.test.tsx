import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ResearchMaterial } from './researchMaterialsModel'
import { AgentMaterialAttachmentPicker } from './AgentMaterialAttachmentPicker'

afterEach(cleanup)

function material(overrides: Partial<ResearchMaterial> = {}): ResearchMaterial {
  return {
    materialId: 'material-ready',
    taskId: 'task-1',
    filename: '社区访谈.docx',
    mediaType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    sizeBytes: 2048,
    status: 'ready',
    version: 1,
    parseVersion: 1,
    segmentCount: 3,
    updatedAt: '2026-09-04T00:00:00Z',
    errorCode: null,
    ...overrides,
  }
}

describe('AgentMaterialAttachmentPicker', () => {
  it('selects ready materials and explains why processing materials are unavailable', () => {
    const onToggle = vi.fn()
    render(
      <AgentMaterialAttachmentPicker
        materials={[
          material(),
          material({ materialId: 'material-processing', filename: '录音.mp3', status: 'processing', parseVersion: null }),
        ]}
        selectedIds={new Set()}
        onToggle={onToggle}
        onClose={vi.fn()}
      />,
    )

    const dialog = screen.getByRole('dialog', { name: '选择本轮材料' })
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /社区访谈\.docx/ }))
    expect(onToggle).toHaveBeenCalledWith(expect.objectContaining({ materialId: 'material-ready' }))
    expect(within(dialog).getByRole('checkbox', { name: /录音\.mp3/ })).toBeDisabled()
    expect(within(dialog).getByText('正在解析，暂时不能附加')).toBeVisible()
  })

  it('surfaces provider-dependent OCR and transcription boundaries', () => {
    render(
      <AgentMaterialAttachmentPicker
        materials={[
          material({ materialId: 'scan', filename: '扫描件.pdf', status: 'failed', unavailableReason: 'ocr_required' }),
          material({ materialId: 'audio', filename: '访谈.wav', status: 'uploaded', unavailableReason: 'transcription_unavailable' }),
        ]}
        selectedIds={new Set()}
        onToggle={vi.fn()}
        onClose={vi.fn()}
      />,
    )

    expect(screen.getByText('需要 OCR，当前未配置，暂不可检索')).toBeVisible()
    expect(screen.getByText('转写服务未配置，暂不可检索')).toBeVisible()
  })
})
