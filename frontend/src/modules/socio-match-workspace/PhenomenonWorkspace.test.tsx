import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { NewResearchPage, PhenomenonWorkspace } from './PhenomenonWorkspace'
import * as api from './researchTaskApi'
import type { PhenomenonCandidate } from './researchTaskModel'

vi.mock('./researchTaskApi')

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

function renderWithQuery(ui: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {ui}
    </QueryClientProvider>,
  )
}

function candidate(overrides: Partial<PhenomenonCandidate> = {}): PhenomenonCandidate {
  return {
    candidateId: 'candidate-1',
    taskId: 'task-1',
    version: 1,
    status: 'proposed',
    contentOrigin: 'system_generated',
    phenomenon: '社区互助为何减少？',
    researchIntent: null,
    context: null,
    missingInformation: [],
    sourceTraceability: 'traceable',
    evidence: [{
      evidenceRefId: 'input:direct',
      excerpt: '社区互助为何减少？',
      locator: null,
      sourceDescription: '用户直接输入',
      useBoundary: '仅代表用户陈述，尚未经外部来源核验。',
    }],
    modelLabel: '演示 AI · deterministic-mock',
    ...overrides,
  }
}

describe('research entry', () => {
  it('shows three entry methods and fills a backend example with visible provenance', async () => {
    vi.mocked(api.listPhenomenonExamplesViaApi).mockResolvedValue([{
      exampleId: 'community-mutual-aid',
      title: '社区互助变化',
      phenomenon: '同一社区中的互助为何逐渐减少？',
      researchIntent: '理解互助关系的变化',
      context: '社区持续更新，成员流动增加',
      sourceType: 'built_in_example',
    }])
    renderWithQuery(<NewResearchPage onStarted={vi.fn()} />)

    expect(screen.getByRole('button', { name: '直接输入' })).toBeVisible()
    expect(screen.getByRole('button', { name: '单份材料' })).toBeVisible()
    expect(screen.getByRole('button', { name: '智能选题' })).toBeVisible()
    fireEvent.click(await screen.findByRole('button', { name: '社区互助变化' }))

    expect(screen.getByLabelText('你观察到的现象')).toHaveValue('同一社区中的互助为何逐渐减少？')
    expect(screen.getByText('当前内容来自内置案例')).toBeVisible()
  })

  it('submits pasted material only after all processing confirmations', async () => {
    vi.mocked(api.listPhenomenonExamplesViaApi).mockResolvedValue([])
    vi.mocked(api.startMaterialViaApi).mockResolvedValue({ taskId: 'task-material' })
    const onStarted = vi.fn()
    renderWithQuery(
      <NewResearchPage
        onStarted={onStarted}
        seedTheory={{ theoryId: 'theory-social-capital', name: '社会资本理论' }}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '单份材料' }))
    fireEvent.change(screen.getByLabelText('粘贴去标识化材料'), {
      target: { value: '第一段观察。\n\n第二段观察。\n\n第三段观察。' },
    })
    fireEvent.click(screen.getByLabelText('我确认材料已去标识化'))
    fireEvent.click(screen.getByLabelText('我有权处理并提交这份材料'))
    fireEvent.click(screen.getByLabelText('我知悉材料可能由外部模型服务处理'))
    fireEvent.click(screen.getByLabelText('我同意当前处理政策版本'))
    fireEvent.click(screen.getByRole('button', { name: '提取现象候选' }))

    await vi.waitFor(() => expect(api.startMaterialViaApi).toHaveBeenCalledOnce())
    expect(vi.mocked(api.startMaterialViaApi).mock.calls[0][0]).toEqual(expect.objectContaining({
      seedTheory: { theoryId: 'theory-social-capital', name: '社会资本理论' },
    }))
    expect(onStarted).toHaveBeenCalledWith('task-material')
  })

  it('keeps smart topic selection as an explicit unavailable placeholder', async () => {
    vi.mocked(api.listPhenomenonExamplesViaApi).mockResolvedValue([])
    renderWithQuery(<NewResearchPage onStarted={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: '智能选题' }))

    expect(screen.getByText('智能选题即将开放')).toBeVisible()
    expect(screen.getByRole('button', { name: '暂未开放' })).toBeDisabled()
  })
})

describe('phenomenon confirmation workspace', () => {
  it('shows the seed clue, candidate provenance and the unconfirmed gate', async () => {
    vi.mocked(api.restorePhenomenonViaApi).mockResolvedValue({
      candidates: [candidate()],
      candidate: candidate(),
      snapshot: null,
      seedTheory: { theoryId: 'theory-social-capital', name: '社会资本理论' },
    })
    renderWithQuery(<PhenomenonWorkspace taskId="task-1" />)

    expect(await screen.findByText('起始线索：社会资本理论')).toBeVisible()
    expect(screen.getByText('系统生成')).toBeVisible()
    expect(screen.getByRole('button', { name: '进入理论匹配' })).toBeDisabled()
    expect(screen.getByText('确认现象后才能进入理论匹配')).toBeVisible()
  })

  it('edits, confirms and keeps the persisted result visible', async () => {
    const restoredCandidate = candidate()
    vi.mocked(api.restorePhenomenonViaApi).mockResolvedValue({
      candidates: [restoredCandidate],
      candidate: restoredCandidate,
      snapshot: null,
      seedTheory: null,
    })
    vi.mocked(api.confirmEditedPhenomenonViaApi).mockResolvedValue({
      phenomenonQueryId: 'query-1',
      phenomenon: '成员流动后，社区互助为何持续减少？',
      researchIntent: null,
      context: null,
      contentHash: 'a'.repeat(64),
      confirmedAt: '2026-08-07T00:00:00Z',
    })
    renderWithQuery(<PhenomenonWorkspace taskId="task-1" />)

    const phenomenon = await screen.findByLabelText('现象表述')
    fireEvent.change(phenomenon, {
      target: { value: '成员流动后，社区互助为何持续减少？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '确认这个现象' }))

    expect(await screen.findByText('现象已经确认并保存')).toBeVisible()
    expect(screen.getByText('用户修改')).toBeVisible()
    expect(screen.getByText('用户直接输入')).toBeVisible()
    expect(screen.getByText('成员流动后，社区互助为何持续减少？')).toBeVisible()
  })

  it('confirms an untouched system candidate without relabeling it', async () => {
    const restoredCandidate = candidate()
    vi.mocked(api.restorePhenomenonViaApi).mockResolvedValue({
      candidates: [restoredCandidate],
      candidate: restoredCandidate,
      snapshot: null,
      seedTheory: null,
    })
    const actualApi = await vi.importActual<typeof import('./researchTaskApi')>(
      './researchTaskApi',
    )
    vi.mocked(api.confirmEditedPhenomenonViaApi).mockImplementation(
      actualApi.confirmEditedPhenomenonViaApi,
    )
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(async () => Response.json({
      task_id: 'task-1',
      phenomenon_query_id: 'query-1',
      version: 2,
      status: 'confirmed',
      allowed_actions: ['start_matching'],
      phenomenon: restoredCandidate.phenomenon,
      research_intent: null,
      context: null,
      source_ref_ids: ['input:direct'],
      evidence_refs: [],
      content_hash: 'a'.repeat(64),
      confirmed_at: '2026-08-08T00:00:00Z',
    }))
    vi.stubGlobal('fetch', fetchMock)
    renderWithQuery(<PhenomenonWorkspace taskId="task-1" />)

    await vi.waitFor(() => expect(screen.getByLabelText('现象表述')).toHaveValue(
      restoredCandidate.phenomenon,
    ))
    fireEvent.click(screen.getByRole('button', { name: '确认这个现象' }))

    expect(await screen.findByText('现象已经确认并保存')).toBeVisible()
    expect(vi.mocked(api.confirmEditedPhenomenonViaApi).mock.calls[0]).toEqual([
      restoredCandidate,
      {
        phenomenon: restoredCandidate.phenomenon,
        researchIntent: '',
        context: '',
      },
    ])
    expect(fetchMock.mock.calls.map(([input]) => {
      const request = input as Request
      return { method: request.method, url: request.url }
    })).toEqual([{
      method: 'POST',
      url: expect.stringContaining('/confirm'),
    }])
    expect(screen.getByText('系统生成')).toBeVisible()
  })
})
