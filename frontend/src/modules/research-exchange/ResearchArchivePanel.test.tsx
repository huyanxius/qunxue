import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResearchArchivePanel } from './ResearchArchivePanel'

const api = vi.hoisted(() => ({
  exportArchive: vi.fn(),
  listAudit: vi.fn(),
  preview: vi.fn(),
}))

vi.mock('./researchExchangeApi', () => ({
  exportResearchArchive: api.exportArchive,
  listResearchAuditEvents: api.listAudit,
  previewQdpxImport: api.preview,
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('ResearchArchivePanel', () => {
  it('shows explicit exchange evidence and previews without restoring', async () => {
    api.listAudit.mockResolvedValue([{
      event_id: 'event-1',
      event_type: 'project.exported',
      object_type: 'research_task',
      object_id: 'task-1',
      object_version: '3',
      actor_type: 'user',
      actor_id: 'user-1',
      payload: { loss_count: 4 },
      occurred_at: '2026-09-01T02:00:00Z',
    }])
    api.exportArchive.mockResolvedValue({
      blob: new Blob(['archive']),
      filename: 'field-study.zip',
      exchangeId: 'exchange-1',
      sha256: 'a'.repeat(64),
      lossCount: 4,
      blockingLossCount: 1,
    })
    api.preview.mockResolvedValue({
      exchange_id: 'exchange-2',
      valid: true,
      validation_scope: 'official-xsd',
      specification_version: '1.0',
      project: {
        name: '外部田野项目',
        origin: 'QualCoder',
        source_count: 2,
        code_count: 3,
        memo_count: 1,
        case_count: 1,
      },
      restored: false,
    })
    const createObjectURL = vi.fn(() => 'blob:archive')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })

    render(<ResearchArchivePanel taskId="task-1" />)

    expect(await screen.findByText('project.exported')).toBeVisible()
    expect(screen.getByRole('heading', { name: '研究归档' })).toBeVisible()
    const exportButton = screen.getByRole('button', { name: '导出研究归档' })
    expect(exportButton).toHaveClass('qx-button', 'qx-button--primary')
    fireEvent.click(exportButton)
    expect(await screen.findByText(/4 项交换损失/)).toBeVisible()
    expect(screen.getByText(/4 项交换损失/).closest('.research-exchange__notice')).toHaveClass('qx-notice-surface')
    expect(api.exportArchive).toHaveBeenCalledWith('task-1')

    const file = new File(['qdpx'], 'external.qdpx', { type: 'application/vnd.qdpx' })
    fireEvent.change(screen.getByLabelText('选择 QDPX 文件'), { target: { files: [file] } })
    await waitFor(() => expect(api.preview).toHaveBeenCalledWith('task-1', file))
    expect(await screen.findByRole('heading', { name: '外部田野项目' })).toBeVisible()
    expect(screen.getByText('只完成校验与预览，未写入当前研究。')).toBeVisible()
  })
})
