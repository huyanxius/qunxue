import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TheoryDecisionWorkspace } from './TheoryDecisionWorkspace'
import * as api from './theoryDecisionApi'
import type { TheoryCandidate, TheoryWorkspace } from './types'

vi.mock('./theoryDecisionApi')

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function candidate(index: number): TheoryCandidate {
  return {
    candidateId: `candidate-${index}`,
    version: 1,
    knowledgeId: `knowledge-${index}`,
    title: `候选理论 ${index}`,
    originLabel: '已审校知识',
    verificationLabel: '来源已核验',
    formalAdoptionEligible: true,
    adoptionBlockers: [],
    problemFocus: '解释社区成员流动与互助变化',
    coreClaims: [`核心命题 ${index}`],
    analysisLevels: ['关系层次'],
    prerequisites: ['持续互动'],
    applicabilityJudgement: 'conditional',
    applicabilityRationale: `AI 判断 ${index}`,
    supportingEvidence: [{
      evidenceRefId: `evidence-${index}`,
      sourceId: `source-${index}`,
      title: `来源 ${index}`,
      verificationStatus: 'verified',
      useBoundary: '只支持当前命题。',
    }],
    missingEvidence: ['缺少长期追踪'],
    limitations: ['不解释宏观政策变化'],
    misuseBoundaries: ['没有互动记录时不适用'],
  }
}

function workspace(count: number): TheoryWorkspace {
  return {
    taskId: 'task-1',
    matchRunId: 'match-1',
    matchRunVersion: 1,
    knowledgeReleaseId: 'release-1',
    status: count ? 'awaiting_decision' : 'no_reliable_candidate',
    completionBasis: 'complete',
    candidates: Array.from({ length: count }, (_, index) => candidate(index + 1)),
    latestDecisionSet: null,
    confirmedPlan: null,
    deferredPlan: null,
  }
}

function renderWorkspace() {
  return render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <TheoryDecisionWorkspace taskId="task-1" />
    </QueryClientProvider>,
  )
}

describe('candidate comparison', () => {
  it.each([0, 1, 3, 8])('renders %i real candidates without a fixed fallback array', async (count) => {
    vi.mocked(api.restoreTheoryWorkspaceViaApi).mockResolvedValue(workspace(count))
    renderWorkspace()

    if (count === 0) {
      expect(await screen.findByText('没有达到资格门槛的候选')).toBeVisible()
      expect(screen.queryAllByRole('article')).toHaveLength(0)
      return
    }
    expect(await screen.findAllByRole('article')).toHaveLength(count)
    expect(screen.getAllByText('AI 适用性判断')).toHaveLength(count)
    expect(screen.getAllByText('你的决定')).toHaveLength(count)
  })

  it('supports every decision action and keeps AI judgement separate from user input', async () => {
    vi.mocked(api.restoreTheoryWorkspaceViaApi).mockResolvedValue(workspace(1))
    vi.mocked(api.saveTheoryDecisionsViaApi).mockResolvedValue({
      decisionSetId: 'decision-set-1',
      version: 1,
    })
    renderWorkspace()

    const selector = await screen.findByLabelText('对候选理论 1 的决定')
    expect(selector).toHaveTextContent('采用')
    expect(selector).toHaveTextContent('排除')
    expect(selector).toHaveTextContent('保留')
    expect(selector).toHaveTextContent('组合')
    expect(selector).toHaveTextContent('暂缓')
    expect(selector).toHaveTextContent('请求补充依据')
    expect(selector).toHaveTextContent('修订适用性')

    fireEvent.change(selector, { target: { value: 'adopt' } })
    fireEvent.change(screen.getByLabelText('决定理由'), {
      target: { value: '它能解释关系资源的变化。' },
    })
    fireEvent.change(screen.getByLabelText('理论角色'), {
      target: { value: 'primary' },
    })
    fireEvent.change(screen.getByLabelText('解释分工'), {
      target: { value: '负责解释互助关系如何形成。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存用户决定' }))

    await vi.waitFor(() => expect(api.saveTheoryDecisionsViaApi).toHaveBeenCalledWith(
      expect.objectContaining({
        matchRunId: 'match-1',
        decisions: [expect.objectContaining({ action: 'adopt' })],
        useAssignments: [expect.objectContaining({ roleCode: 'primary' })],
      }),
      expect.anything(),
    ))
  })

  it('requires relationship and division of labour before confirming multiple theories', async () => {
    vi.mocked(api.restoreTheoryWorkspaceViaApi).mockResolvedValue(workspace(3))
    renderWorkspace()

    await screen.findByText('候选理论 1')
    for (const selector of screen.getAllByLabelText(/的决定$/).slice(0, 2)) {
      fireEvent.change(selector, { target: { value: 'combine' } })
    }

    expect(screen.getByText('多理论关系')).toBeVisible()
    expect(screen.getByLabelText('关系类型')).toBeRequired()
    expect(screen.getByLabelText('关系说明')).toBeRequired()
    expect(screen.getAllByLabelText('理论角色')).toHaveLength(2)
    expect(screen.getAllByLabelText('解释分工')).toHaveLength(2)
  })

  it('builds a knowledge detail round trip back to the same matching workspace', async () => {
    vi.mocked(api.restoreTheoryWorkspaceViaApi).mockResolvedValue(workspace(1))
    renderWorkspace()

    const link = await screen.findByRole('link', { name: '查看知识详情' })
    expect(link).toHaveAttribute(
      'href',
      '/knowledge/knowledge-1?knowledge_release_id=release-1&return_to=%2Fresearch%2Ftask-1%2Fmatch',
    )
  })

  it('restores role, division of labour and relationship inputs after refresh', async () => {
    vi.mocked(api.restoreTheoryWorkspaceViaApi).mockResolvedValue({
      ...workspace(3),
      latestDecisionSet: {
        decisionSetId: 'set-1', version: 1,
        decisions: [
          { candidateId: 'candidate-1', action: 'combine', reason: '联合解释', revisedApplicability: null },
          { candidateId: 'candidate-2', action: 'combine', reason: '联合解释', revisedApplicability: null },
          { candidateId: 'candidate-3', action: 'exclude', reason: '不适用', revisedApplicability: null },
        ],
        useAssignments: [
          { candidateId: 'candidate-1', roleCode: 'primary', responsibility: '核心解释' },
          { candidateId: 'candidate-2', roleCode: 'complementary', responsibility: '补充解释' },
        ],
        relations: [{
          candidateIds: ['candidate-1', 'candidate-2'], relationKind: 'complementary',
          explanation: '层次互补', premiseCompatibility: '兼容', supportingEvidence: ['支持'],
          excludingEvidence: ['排除'], distinguishingEvidence: ['区分'],
        }],
      },
    })
    renderWorkspace()

    expect((await screen.findAllByLabelText('理论角色'))[0]).toHaveValue('primary')
    expect(screen.getByLabelText('关系类型')).toHaveValue('complementary')
    expect(screen.getByLabelText('关系说明')).toHaveValue('层次互补')
  })

  it('defers the whole plan and shows restored deferral state', async () => {
    vi.mocked(api.restoreTheoryWorkspaceViaApi).mockResolvedValue(workspace(1))
    vi.mocked(api.deferTheoryPlanViaApi).mockResolvedValue({
      reason: '等待补充材料', deferredAt: '2026-08-11T00:00:00Z',
    })
    renderWorkspace()

    fireEvent.change(await screen.findByLabelText('整体暂缓理由'), {
      target: { value: '等待补充材料' },
    })
    fireEvent.click(screen.getByRole('button', { name: '暂缓整个理论方案' }))

    await vi.waitFor(() => expect(api.deferTheoryPlanViaApi).toHaveBeenCalledWith({
      matchRunId: 'match-1', matchRunVersion: 1, reason: '等待补充材料',
    }, expect.anything()))
    expect(await screen.findByText('已暂缓：等待补充材料')).toBeVisible()
  })
})
