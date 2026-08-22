import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  M4TheoryJudgment,
  M4TheoryJudgmentFailure,
  type M4ConfirmedPlan,
  type M4DecisionDraft,
  type M4TheoryJudgmentGateway,
  type M4Workspace,
} from './M4TheoryJudgment'

const evidence = {
  evidenceRefId: 'evidence-1',
  claim: '时间紧缩会挤压非正式互助。',
  excerpt: '访谈反复提到下班后无法参与社区互助。',
  locator: '第 3 章，p. 47',
  sourceId: 'source-1',
  sourceTitle: '社区关系与时间压力',
  sourceUrl: 'https://example.org/source-1',
  verificationStatus: 'verified' as const,
  useBoundary: '只支持工作时间与互助频率的关联，不证明因果。',
}

const candidate = {
  candidateId: 'candidate-1',
  version: 3,
  title: '时间贫困理论',
  problemFocus: '时间资源分配如何改变关系维护。',
  coreClaims: ['个体的可支配时间受制度性安排影响。'],
  analysisLevels: ['个体', '社区'],
  prerequisites: ['互助需要持续的时间投入。'],
  applicabilityJudgement: 'applicable' as const,
  applicabilityRationale: '与已确认现象中的工时延长和互助减少直接对应。',
  supportingEvidence: [evidence],
  conflictingEvidence: [{ ...evidence, evidenceRefId: 'evidence-2', claim: '一些长工时居民仍维持高频互助。', locator: '附录 B，p. 12' }],
  missingEvidence: ['不同职业群体的可支配时间记录。'],
  requestedMaterial: ['连续两周的时间日志。'],
  limitations: ['无法单独解释互惠规范的差异。'],
  misuseBoundaries: ['不应将所有互助减少归因于个人时间管理。'],
  competingTheories: [{ theoryId: 'theory-2', title: '社会资本理论', explanation: '将互助减少解释为网络弱化。' }],
  complementaryTheories: [{ theoryId: 'theory-3', title: '互惠规范理论', explanation: '补充解释行动者为何仍愿意互助。' }],
  sourceIds: ['source-1'],
  reviewStatus: 'pre_review_completed' as const,
  formalAdoptionEligible: true,
  adoptionBlockers: [],
  modelLabel: 'Qwen · production-v2',
  modelTraceId: 'trace-1',
}

function draft(overrides: Partial<M4DecisionDraft> = {}): M4DecisionDraft {
  return {
    matchRunId: 'match-1',
    version: 4,
    updatedAt: '2026-08-22T08:00:00Z',
    partialAcknowledgementReason: '',
    decisions: [{
      candidateId: 'candidate-1',
      candidateVersion: 3,
      action: 'adopt',
      reason: '工时与互助频率的变化具有直接对应，但仍需补充时间日志。',
      roleCode: 'primary',
      responsibility: '解释时间约束如何压缩互助行动。',
      relatedSourceIds: ['source-1'],
      revisedApplicability: '',
    }],
    relation: {
      explanation: '',
      premiseCompatibility: '',
      supportingEvidence: '',
      excludingEvidence: '',
      distinguishingEvidence: '',
    },
    ...overrides,
  }
}

function workspace(overrides: Partial<M4Workspace> = {}): M4Workspace {
  return {
    matchRun: {
      matchRunId: 'match-1',
      taskId: 'task-1',
      version: 6,
      status: 'awaiting_decision',
      knowledgeReleaseId: 'release-final-20260822',
      completionBasis: 'complete',
      partialCompletionAcknowledged: false,
      failedCandidates: [],
      candidates: [candidate],
    },
    draft: draft(),
    decisionSet: null,
    confirmedPlan: null,
    ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

function gateway(initial: M4Workspace = workspace()): M4TheoryJudgmentGateway {
  return {
    start: vi.fn().mockResolvedValue(initial),
    restore: vi.fn().mockResolvedValue(initial),
    saveDraft: vi.fn().mockImplementation(async (request) => ({
      ...request.draft,
      version: request.expectedVersion + 1,
      updatedAt: '2026-08-22T08:01:00Z',
    })),
    retryCandidate: vi.fn().mockResolvedValue(initial),
    acknowledgePartial: vi.fn().mockResolvedValue({
      ...initial,
      matchRun: { ...initial.matchRun, status: 'awaiting_decision', partialCompletionAcknowledged: true },
    }),
    createDecisionSet: vi.fn().mockResolvedValue({
      decisionSetId: 'decision-set-1',
      version: 1,
      canConfirm: true,
      knowledgeReleaseId: 'release-final-20260822',
    }),
    confirmPlan: vi.fn().mockResolvedValue({
      theoryPlanId: 'plan-1',
      taskId: 'task-1',
      matchRunId: 'match-1',
      decisionSetId: 'decision-set-1',
      knowledgeReleaseId: 'release-final-20260822',
      confirmedAt: '2026-08-22T08:02:00Z',
    }),
  }
}

describe('M4TheoryJudgment', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }))
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('restores the server draft and exposes complete fit, risk, provenance, and user-owned fields', async () => {
    const service = gateway()
    render(<M4TheoryJudgment task={{ taskId: 'task-1', taskVersion: 7, matchRunId: 'match-1', theoryPlanId: null, phenomenonQueryId: 'phenomenon-1', phenomenonVersion: 2, canStartMatching: false }} gateway={service} />)

    const card = await screen.findByRole('article', { name: '候选理论：时间贫困理论' })
    expect(within(card).getByText('时间资源分配如何改变关系维护。')).toBeVisible()
    expect(within(card).getByText('互助需要持续的时间投入。')).toBeVisible()
    expect(within(card).getByText('一些长工时居民仍维持高频互助。')).toBeVisible()
    expect(within(card).getByText('不同职业群体的可支配时间记录。')).toBeVisible()
    expect(within(card).getByText('无法单独解释互惠规范的差异。')).toBeVisible()
    expect(within(card).getByText('不应将所有互助减少归因于个人时间管理。')).toBeVisible()
    expect(within(card).getByText('社会资本理论')).toBeVisible()
    const reviewStatus = within(card).getByRole('note', { name: /档案审核状态/ })
    expect(reviewStatus).toHaveTextContent('预审核完成')
    expect(reviewStatus).toHaveTextContent('仅供内测，后续仍可继续深度复核')
    expect(reviewStatus).not.toHaveTextContent('专家终审')
    expect(reviewStatus).not.toHaveTextContent('全面审核')
    expect(within(card).getAllByRole('link', { name: /社区关系与时间压力/ })[0]).toHaveAttribute('href', 'https://example.org/source-1')
    expect(within(card).getByText('第 3 章，p. 47')).toBeVisible()
    expect(screen.getByLabelText('选择时间贫困理论的理由')).toHaveValue('工时与互助频率的变化具有直接对应，但仍需补充时间日志。')
    expect(screen.getByLabelText('时间贫困理论在方案中的作用')).toHaveValue('解释时间约束如何压缩互助行动。')
    expect(screen.getByText(/release-final-20260822/)).toBeVisible()
    expect(screen.getByText(/trace-1/)).toBeVisible()
  })

  it('does not mislabel a candidate without the pre-review-completed status', async () => {
    const unreviewed = workspace({
      matchRun: {
        ...workspace().matchRun,
        candidates: [{ ...candidate, reviewStatus: null }],
      },
    })
    render(<M4TheoryJudgment task={{ taskId: 'task-1', taskVersion: 7, matchRunId: 'match-1', theoryPlanId: null, phenomenonQueryId: 'phenomenon-1', phenomenonVersion: 2, canStartMatching: false }} gateway={gateway(unreviewed)} />)

    await screen.findByRole('article', { name: '候选理论：时间贫困理论' })
    expect(screen.queryByRole('note', { name: /档案审核状态/ })).not.toBeInTheDocument()
    expect(screen.queryByText('预审核完成')).not.toBeInTheDocument()
  })

  it('keeps claim-level evidence while listing each selectable source only once', async () => {
    const repeatedSource = workspace({
      matchRun: {
        ...workspace().matchRun,
        candidates: [{
          ...candidate,
          supportingEvidence: [evidence, { ...evidence, evidenceRefId: 'evidence-3', claim: '同一来源支持的第二条主张。' }],
        }],
      },
    })
    render(<M4TheoryJudgment task={{ taskId: 'task-1', taskVersion: 7, matchRunId: 'match-1', theoryPlanId: null, phenomenonQueryId: 'phenomenon-1', phenomenonVersion: 2, canStartMatching: false }} gateway={gateway(repeatedSource)} />)

    const card = await screen.findByRole('article', { name: '候选理论：时间贫困理论' })
    expect(within(card).getAllByRole('link', { name: /社区关系与时间压力/ })).toHaveLength(3)
    expect(within(card).getAllByRole('checkbox', { name: '社区关系与时间压力' })).toHaveLength(1)
  })

  it('autosaves edits with the restored revision and invalidates an older confirmable decision', async () => {
    const initial = workspace({
      decisionSet: { decisionSetId: 'old-decision-set', version: 2, canConfirm: true, knowledgeReleaseId: 'release-final-20260822' },
    })
    const service = gateway(initial)
    render(<M4TheoryJudgment task={{ taskId: 'task-1', taskVersion: 7, matchRunId: 'match-1', theoryPlanId: null, phenomenonQueryId: 'phenomenon-1', phenomenonVersion: 2, canStartMatching: false }} gateway={service} />)

    const reason = await screen.findByLabelText('选择时间贫困理论的理由')
    expect(screen.getByRole('button', { name: '确认理论方案' })).toBeEnabled()
    fireEvent.change(reason, { target: { value: '我修改了理由，需要重新形成决定。' } })
    expect(screen.queryByRole('button', { name: '确认理论方案' })).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('尚未保存')

    await vi.advanceTimersByTimeAsync(750)
    await waitFor(() => expect(service.saveDraft).toHaveBeenCalledTimes(1))
    expect(vi.mocked(service.saveDraft).mock.calls[0][0]).toEqual(expect.objectContaining({
      matchRunId: 'match-1',
      expectedVersion: 4,
      draft: expect.objectContaining({ decisions: [expect.objectContaining({ reason: '我修改了理由，需要重新形成决定。' })] }),
    }))
    expect(await screen.findByText('已保存到云端')).toBeVisible()
  })

  it('survives an autosave conflict by restoring the newer server draft', async () => {
    const newer = draft({ version: 8, decisions: [{ ...draft().decisions[0], reason: '另一个页面已保存的更新理由。' }] })
    const service = gateway()
    vi.mocked(service.saveDraft).mockRejectedValueOnce(new M4TheoryJudgmentFailure('draft_conflict', '草稿版本冲突。', { workspace: workspace({ draft: newer }) }))
    render(<M4TheoryJudgment task={{ taskId: 'task-1', taskVersion: 7, matchRunId: 'match-1', theoryPlanId: null, phenomenonQueryId: 'phenomenon-1', phenomenonVersion: 2, canStartMatching: false }} gateway={service} />)

    fireEvent.change(await screen.findByLabelText('选择时间贫困理论的理由'), { target: { value: '本页的未保存理由。' } })
    await vi.advanceTimersByTimeAsync(750)

    expect(await screen.findByRole('alert')).toHaveTextContent('其他页面已保存更新版本')
    expect(screen.getByLabelText('选择时间贫困理论的理由')).toHaveValue('另一个页面已保存的更新理由。')
  })

  it.each([
    ['catalog_not_ready', '知识目录尚无可用的正式发布', '重试检查', '只有预审核完成并发布为内测固定版本的理论档案才会进入匹配。'],
    ['network', '网络中断；如果正在编辑，请保持本页打开并在恢复连接后重试保存。', '重新连接', '恢复连接后会从服务器继续，不会生成静态候选。'],
    ['model_failed', '理论判断服务本次未完成', '重试匹配', '本次失败不会成为研究结论。'],
  ] as const)('shows a recoverable %s start failure without presenting fabricated candidates', async (code, message, action, detail) => {
    const service = gateway()
    vi.mocked(service.start).mockRejectedValueOnce(new M4TheoryJudgmentFailure(code, message))
    render(<M4TheoryJudgment task={{ taskId: 'task-1', taskVersion: 7, matchRunId: null, theoryPlanId: null, phenomenonQueryId: 'phenomenon-1', phenomenonVersion: 2, canStartMatching: true }} gateway={service} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByRole('alert')).toHaveTextContent(detail)
    expect(screen.getByRole('button', { name: action })).toBeEnabled()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })

  it('gives no-reliable-candidate a truthful exit and retry path', async () => {
    const noCandidate = workspace({ matchRun: { ...workspace().matchRun, status: 'no_reliable_candidate', candidates: [] }, draft: draft({ decisions: [] }) })
    const service = gateway(noCandidate)
    render(<M4TheoryJudgment task={{ taskId: 'task-1', taskVersion: 7, matchRunId: 'match-1', theoryPlanId: null, phenomenonQueryId: 'phenomenon-1', phenomenonVersion: 2, canStartMatching: false }} gateway={service} />)

    expect(await screen.findByText('暂时没有足够可靠的候选理论')).toBeVisible()
    expect(screen.getByText('你可以返回补充现象材料，或稍后重新匹配。')).toBeVisible()
    expect(screen.getByRole('button', { name: '重新检查候选' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: '保存完整理论决定' })).not.toBeInTheDocument()
  })

  it('keeps partial failure explicit, retries a failed candidate, and requires the user acknowledgement reason', async () => {
    const partial = workspace({
      matchRun: {
        ...workspace().matchRun,
        status: 'partial_failure',
        completionBasis: 'partial',
        failedCandidates: [{ candidateId: 'candidate-2', version: 1, title: '社会资本理论', failureCode: 'model_timeout', retryable: true }],
      },
    })
    const retried = workspace()
    const service = gateway(partial)
    vi.mocked(service.retryCandidate).mockResolvedValueOnce(retried)
    render(<M4TheoryJudgment task={{ taskId: 'task-1', taskVersion: 7, matchRunId: 'match-1', theoryPlanId: null, phenomenonQueryId: 'phenomenon-1', phenomenonVersion: 2, canStartMatching: false }} gateway={service} />)

    const failure = await screen.findByRole('alert')
    expect(failure).toHaveTextContent('1 个候选未完成')
    expect(screen.getByRole('button', { name: '重试社会资本理论' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '确认以当前候选继续' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('继续使用部分候选的理由'), { target: { value: '已了解未完成候选的风险，先用已有证据继续。' } })
    expect(screen.getByRole('button', { name: '确认以当前候选继续' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: '重试社会资本理论' }))
    await waitFor(() => expect(service.retryCandidate).toHaveBeenCalledOnce())
    expect(await screen.findByText('所有候选已完成判断')).toBeVisible()
  })

  it('persists an edited partial acknowledgement before advancing to the server draft version', async () => {
    const partial = workspace({
      matchRun: {
        ...workspace().matchRun,
        status: 'partial_failure',
        completionBasis: 'partial',
        failedCandidates: [{ candidateId: 'candidate-2', version: 1, title: '社会资本理论', failureCode: 'model_timeout', retryable: true }],
      },
    })
    const save = deferred<M4DecisionDraft>()
    const acknowledged = workspace({
      matchRun: {
        ...partial.matchRun,
        version: 7,
        status: 'awaiting_decision',
        completionBasis: 'partial_with_user_ack',
        partialCompletionAcknowledged: true,
      },
      draft: draft({ version: 6, partialAcknowledgementReason: '先使用当前可靠候选，并保留未完成项的风险。' }),
    })
    const service = gateway(partial)
    vi.mocked(service.saveDraft).mockReturnValueOnce(save.promise)
    vi.mocked(service.acknowledgePartial).mockResolvedValueOnce(acknowledged)
    render(<M4TheoryJudgment task={{ taskId: 'task-1', taskVersion: 7, matchRunId: 'match-1', theoryPlanId: null, phenomenonQueryId: 'phenomenon-1', phenomenonVersion: 2, canStartMatching: false }} gateway={service} />)

    const reason = await screen.findByLabelText('继续使用部分候选的理由')
    fireEvent.change(reason, { target: { value: '先使用当前可靠候选，并保留未完成项的风险。' } })
    fireEvent.click(screen.getByRole('button', { name: '确认以当前候选继续' }))

    expect(service.saveDraft).toHaveBeenCalledOnce()
    expect(service.acknowledgePartial).not.toHaveBeenCalled()
    save.resolve(draft({ version: 5, partialAcknowledgementReason: '先使用当前可靠候选，并保留未完成项的风险。' }))
    await waitFor(() => expect(service.acknowledgePartial).toHaveBeenCalledOnce())
    expect(vi.mocked(service.saveDraft).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(service.acknowledgePartial).mock.invocationCallOrder[0])
    expect(await screen.findByText('已记录你继续使用部分候选的理由。')).toBeVisible()
    expect(screen.getByText(/已保存到云端/)).toBeVisible()
  })

  it('locks repeated confirmation and emits the one confirmed plan returned by the server', async () => {
    const service = gateway()
    const confirmation = deferred<M4ConfirmedPlan>()
    vi.mocked(service.confirmPlan).mockReturnValueOnce(confirmation.promise)
    const onConfirmed = vi.fn()
    render(<M4TheoryJudgment task={{ taskId: 'task-1', taskVersion: 7, matchRunId: 'match-1', theoryPlanId: null, phenomenonQueryId: 'phenomenon-1', phenomenonVersion: 2, canStartMatching: false }} gateway={service} onConfirmed={onConfirmed} />)

    fireEvent.click(await screen.findByRole('button', { name: '保存完整理论决定' }))
    const confirm = await screen.findByRole('button', { name: '确认理论方案' })
    fireEvent.click(confirm)
    fireEvent.click(confirm)

    expect(service.confirmPlan).toHaveBeenCalledTimes(1)
    expect(confirm).toBeDisabled()
    confirmation.resolve({ theoryPlanId: 'plan-1', taskId: 'task-1', matchRunId: 'match-1', decisionSetId: 'decision-set-1', knowledgeReleaseId: 'release-final-20260822', confirmedAt: '2026-08-22T08:02:00Z' })
    expect(await screen.findByText('理论方案已确认')).toBeVisible()
    expect(onConfirmed).toHaveBeenCalledTimes(1)
    expect(onConfirmed).toHaveBeenCalledWith(expect.objectContaining({ theoryPlanId: 'plan-1', knowledgeReleaseId: 'release-final-20260822' }))
  })
})
