import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { NewResearchPage, PhenomenonWorkspace } from './PhenomenonWorkspace'
import * as api from './researchTaskApi'

vi.mock('./researchTaskApi')

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderWithQuery(ui: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {ui}
    </QueryClientProvider>,
  )
}

describe('phenomenon confirmation workspace', () => {
  it('starts from direct input and opens the editable candidate', async () => {
    vi.mocked(api.startPhenomenonViaApi).mockResolvedValue({
      taskId: 'task-1',
      candidate: {} as never,
    })
    const onStarted = vi.fn()
    renderWithQuery(<NewResearchPage onStarted={onStarted} />)

    fireEvent.change(screen.getByLabelText('你观察到的现象'), {
      target: { value: '社区互助为何减少？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '生成可编辑候选' }))

    await vi.waitFor(() => expect(onStarted).toHaveBeenCalledWith('task-1'))
  })

  it('edits, confirms and keeps the persisted result visible', async () => {
    const candidate = {
      candidateId: 'candidate-1',
      taskId: 'task-1',
      version: 1,
      status: 'proposed' as const,
      phenomenon: '社区互助为何减少？',
      researchIntent: null,
      context: null,
      evidence: [{
        evidenceRefId: 'input:direct',
        excerpt: '社区互助为何减少？',
        sourceDescription: '用户直接输入',
        useBoundary: '仅代表用户陈述，尚未经外部来源核验。',
      }],
      modelLabel: '演示 AI · deterministic-mock',
    }
    vi.mocked(api.restorePhenomenonViaApi).mockResolvedValue({
      candidate,
      snapshot: null,
    })
    vi.mocked(api.confirmEditedPhenomenonViaApi).mockResolvedValue({
      phenomenonQueryId: 'query-1',
      phenomenon: '成员流动后，社区互助为何持续减少？',
      researchIntent: null,
      context: null,
      confirmedAt: '2026-08-07T00:00:00Z',
    })
    renderWithQuery(<PhenomenonWorkspace taskId="task-1" />)

    const phenomenon = await screen.findByLabelText('现象表述')
    fireEvent.change(phenomenon, {
      target: { value: '成员流动后，社区互助为何持续减少？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '确认这个现象' }))

    expect(await screen.findByText('现象已经确认并保存')).toBeVisible()
    expect(screen.getByText('演示 AI · deterministic-mock')).toBeVisible()
    expect(screen.getByText('用户直接输入')).toBeVisible()
    expect(screen.getByText('成员流动后，社区互助为何持续减少？')).toBeVisible()
  })
})
