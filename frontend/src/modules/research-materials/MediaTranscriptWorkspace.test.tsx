import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { MediaTranscriptWorkspace } from './MediaTranscriptWorkspace'

const getTranscriptionWorkspace = vi.fn()
const importTranscript = vi.fn()
const createCorrectedTranscriptVersion = vi.fn()

vi.mock('./transcriptionApi', () => ({
  mediaContentUrl: (taskId: string, materialId: string) => `/api/research-tasks/${taskId}/materials/${materialId}/content`,
  getTranscriptionWorkspace: (...args: unknown[]) => getTranscriptionWorkspace(...args),
  importTranscript: (...args: unknown[]) => importTranscript(...args),
  createCorrectedTranscriptVersion: (...args: unknown[]) => createCorrectedTranscriptVersion(...args),
  startAutomaticTranscription: vi.fn(),
}))

const version = {
  versionId: 'version-1',
  materialId: 'material-1',
  version: 1,
  source: 'imported' as const,
  provider: null,
  createdFromVersionId: null,
  createdAt: '2026-09-01T10:00:00Z',
  isCurrent: true,
  segments: [
    { segmentId: 'segment-1', ordinal: 0, speaker: '主持人', startMs: 1_250, endMs: 3_800, text: '请先介绍一下自己。' },
    { segmentId: 'segment-2', ordinal: 1, speaker: '受访者', startMs: 4_100, endMs: 6_900, text: '我在这里住了十年。' },
  ],
}

describe('MediaTranscriptWorkspace', () => {
  afterEach(cleanup)

  beforeEach(() => {
    vi.clearAllMocks()
    getTranscriptionWorkspace.mockResolvedValue({
      materialId: 'material-1',
      status: 'ready',
      automaticAvailable: false,
      automaticProvider: null,
      errorCode: null,
      currentVersion: version,
      versions: [version],
    })
  })

  it('seeks the original media when a timed transcript segment is selected', async () => {
    render(<MediaTranscriptWorkspace taskId="task-1" materialId="material-1" mediaType="audio/wav" />)

    const player = await screen.findByLabelText('原始媒体') as HTMLMediaElement
    fireEvent.click(screen.getByRole('button', { name: /00:01.250.*主持人/ }))

    expect(player.currentTime).toBe(1.25)
  })

  it('keeps manual import available when automatic transcription is unavailable', async () => {
    render(<MediaTranscriptWorkspace taskId="task-1" materialId="material-1" mediaType="audio/wav" />)

    expect(await screen.findByText('自动转写服务未配置')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '导入转录稿' })).toBeEnabled()
  })

  it('opens a material citation at its immutable transcript segment', async () => {
    render(
      <MediaTranscriptWorkspace
        taskId="task-1"
        materialId="material-1"
        mediaType="audio/wav"
        initialParseId="version-1"
        initialSegmentId="segment-2"
      />,
    )

    const target = await screen.findByRole('button', { name: /00:04.100.*受访者/ })
    const player = screen.getByLabelText('原始媒体') as HTMLMediaElement
    expect(target).toHaveAttribute('aria-current', 'location')
    expect(player.currentTime).toBe(4.1)
  })

  it('saves speaker and text corrections as a new version', async () => {
    const corrected = { ...version, versionId: 'version-2', version: 2, source: 'manual_correction' as const, isCurrent: true }
    createCorrectedTranscriptVersion.mockResolvedValue(corrected)
    getTranscriptionWorkspace
      .mockResolvedValueOnce({
        materialId: 'material-1', status: 'ready', automaticAvailable: false,
        automaticProvider: null, errorCode: null, currentVersion: version, versions: [version],
      })
      .mockResolvedValueOnce({
        materialId: 'material-1', status: 'ready', automaticAvailable: false,
        automaticProvider: null, errorCode: null, currentVersion: corrected,
        versions: [corrected, { ...version, isCurrent: false }],
      })
    render(<MediaTranscriptWorkspace taskId="task-1" materialId="material-1" mediaType="audio/wav" />)

    fireEvent.click(await screen.findByRole('button', { name: '校订当前版本' }))
    fireEvent.change(screen.getByLabelText('第 1 段说话人'), { target: { value: '访谈员' } })
    fireEvent.change(screen.getByLabelText('第 1 段文字'), { target: { value: '请先简单介绍一下自己。' } })
    fireEvent.click(screen.getByRole('button', { name: '保存为新版本' }))

    await waitFor(() => expect(createCorrectedTranscriptVersion).toHaveBeenCalledWith(
      'task-1',
      'material-1',
      'version-1',
      expect.arrayContaining([expect.objectContaining({ speaker: '访谈员', text: '请先简单介绍一下自己。' })]),
    ))
    await waitFor(() => expect(screen.getByRole('combobox', { name: '转录版本' })).toHaveValue('version-2'))
  })
})
