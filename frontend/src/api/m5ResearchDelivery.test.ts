import { beforeEach, describe, expect, it, vi } from 'vitest'

const generated = vi.hoisted(() => ({
  acceptResearchDocumentProposal: vi.fn(),
  confirmResearchDocument: vi.fn(),
  createResearchDocument: vi.fn(),
  exportResearchDocument: vi.fn(),
  getResearchDocumentCompletionGate: vi.fn(),
  listResearchDocuments: vi.fn(),
  listResearchDocumentVersions: vi.fn(),
  listResearchTaskDocumentProposals: vi.fn(),
  rejectResearchDocumentProposal: vi.fn(),
  restoreResearchDocument: vi.fn(),
  updateResearchDocument: vi.fn(),
}))

vi.mock('./generated', () => generated)
vi.mock('./client', () => ({ apiClient: { adapter: 'test' } }))

import {
  loadM5ResearchDelivery,
  saveM5ResearchDocument,
  serializeM5ResearchExport,
} from './m5ResearchDelivery'

function ok<T>(data: T) {
  return Promise.resolve({ data, error: undefined, response: new Response(null, { status: 200 }) })
}

function document(overrides: Record<string, unknown> = {}) {
  return {
    document_id: 'document-7',
    task_id: 'task-7',
    theory_plan_id: 'plan-7',
    title: '正式研究框架',
    version: 4,
    status: 'draft',
    sections: [],
    ...overrides,
  }
}

function proposal(overrides: Record<string, unknown> = {}) {
  return {
    proposal_id: 'proposal-7',
    agent_run_id: 'run-7',
    model_provider: 'openai-compatible',
    model_name: 'research-model-v1',
    base_document_version: null,
    conversation_id: 'conversation-7',
    created_at: '2026-08-22T04:00:00Z',
    decided_at: null,
    decision_reason: null,
    document_id: null,
    kind: 'create',
    knowledge_release_id: 'release-7',
    proposed_sections: [],
    rationale: '根据已确认理论方案生成。',
    requires_user_approval: true,
    result_document_id: null,
    result_document_version: null,
    status: 'pending',
    target_section_id: null,
    task_id: 'task-7',
    theory_plan_id: 'plan-7',
    title: '创建正式研究框架',
    user_id: 'user-7',
    ...overrides,
  }
}

describe('M5 research delivery adapter', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads only the confirmed plan and exposes an explainable completion projection', async () => {
    generated.listResearchDocuments.mockReturnValue(ok({
      task_id: 'task-7',
      items: [document(), document({ document_id: 'document-other', theory_plan_id: 'plan-other' })],
    }))
    generated.listResearchTaskDocumentProposals.mockReturnValue(ok({
      task_id: 'task-7',
      items: [
        proposal({ status: 'rejected' }),
        proposal({ proposal_id: 'proposal-other', theory_plan_id: 'plan-other' }),
      ],
    }))
    generated.listResearchDocumentVersions.mockReturnValue(ok({
      document_id: 'document-7',
      items: [document(), document({ version: 3 })],
    }))
    generated.getResearchDocumentCompletionGate.mockReturnValue(ok({
      document_id: 'document-7',
      version: 4,
      ready: false,
      pending_proposal_count: 0,
      blockers: ['伦理说明尚未审阅'],
      checks: [{ code: 'required_sections_reviewed', label: '规定章节已审阅', passed: false, detail: '伦理说明尚未审阅' }],
    }))

    const state = await loadM5ResearchDelivery({
      taskId: 'task-7',
      confirmedTheoryPlanId: 'plan-7',
    })

    expect(state.phase).toBe('editing')
    expect(state.document?.documentId).toBe('document-7')
    expect(state.proposals.map((item) => item.proposalId)).toEqual(['proposal-7'])
    expect(state.proposals[0]).toEqual(expect.objectContaining({
      modelProvider: 'openai-compatible',
      modelName: 'research-model-v1',
    }))
    expect(state.versions).toHaveLength(2)
    expect(state.completion).toEqual(expect.objectContaining({
      completed: false,
      ready: false,
      documentId: 'document-7',
      version: 4,
      blockers: ['伦理说明尚未审阅'],
    }))
  })

  it('does not invent a document while generation or approval is pending', async () => {
    generated.listResearchDocuments.mockReturnValue(ok({ task_id: 'task-7', items: [] }))
    generated.listResearchTaskDocumentProposals.mockReturnValue(ok({
      task_id: 'task-7',
      items: [proposal()],
    }))

    const state = await loadM5ResearchDelivery({ taskId: 'task-7', confirmedTheoryPlanId: 'plan-7' })

    expect(state.phase).toBe('awaiting_review')
    expect(state.document).toBeNull()
    expect(state.completion).toEqual(expect.objectContaining({
      ready: false,
      completed: false,
      blockers: ['请先审批待处理的 Agent 建议。'],
    }))
    expect(generated.getResearchDocumentCompletionGate).not.toHaveBeenCalled()
    expect(generated.listResearchDocumentVersions).not.toHaveBeenCalled()
  })

  it('projects the confirmed analysis snapshot pinned to the current document version', async () => {
    generated.listResearchDocuments.mockReturnValue(ok({
      task_id: 'task-7',
      items: [document({
        research_analysis: {
          schema_version: 'research-analysis-v1',
          task_id: 'task-7',
          content_hash: 'sha256:analysis-4',
          annotations: [],
          codes: [{ code_id: 'code-1', label: '时间压力', definition: '准备时间不足。' }],
          memos: [{ memo_id: 'memo-1', title: '资源分布', memo_kind: 'analytic' }],
          comparisons: [{
            comparison_id: 'comparison-1',
            title: '案例差异',
            theory_implication: '需要区分正式支持与同伴网络。',
          }],
          unavailable_annotation_ids: ['annotation-deleted'],
        },
      })],
    }))
    generated.listResearchTaskDocumentProposals.mockReturnValue(ok({ task_id: 'task-7', items: [] }))
    generated.listResearchDocumentVersions.mockReturnValue(ok({ document_id: 'document-7', items: [] }))
    generated.getResearchDocumentCompletionGate.mockReturnValue(ok({
      document_id: 'document-7',
      version: 4,
      ready: false,
      pending_proposal_count: 0,
      blockers: [],
      checks: [],
    }))

    const state = await loadM5ResearchDelivery({ taskId: 'task-7', confirmedTheoryPlanId: 'plan-7' })

    expect(state.document?.analysisBasis).toEqual({
      contentHash: 'sha256:analysis-4',
      codes: [{ id: 'code-1', label: '时间压力', definition: '准备时间不足。' }],
      memos: [{ id: 'memo-1', title: '资源分布', kindLabel: '分析备忘' }],
      comparisons: [{
        id: 'comparison-1',
        title: '案例差异',
        theoryImplication: '需要区分正式支持与同伴网络。',
      }],
      unavailableAnnotationCount: 1,
    })
  })

  it('rejects duplicate M5 documents instead of selecting an arbitrary state source', async () => {
    generated.listResearchDocuments.mockReturnValue(ok({
      task_id: 'task-7',
      items: [document(), document({ document_id: 'document-8' })],
    }))
    generated.listResearchTaskDocumentProposals.mockReturnValue(ok({ task_id: 'task-7', items: [] }))

    await expect(loadM5ResearchDelivery({ taskId: 'task-7', confirmedTheoryPlanId: 'plan-7' }))
      .rejects.toThrow('检测到多份 M5 文档')
  })

  it('preserves caller-owned CAS and idempotency values on save', async () => {
    generated.updateResearchDocument.mockReturnValue(ok(document({ version: 5 })))

    await saveM5ResearchDocument({
      documentId: 'document-7',
      expectedVersion: 4,
      idempotencyKey: 'save-attempt-4',
      sections: [],
      changeSummary: '补充抽样策略',
    })

    expect(generated.updateResearchDocument).toHaveBeenCalledWith(expect.objectContaining({
      client: { adapter: 'test' },
      path: { document_id: 'document-7' },
      headers: { 'Idempotency-Key': 'save-attempt-4' },
      body: {
        expected_version: 4,
        sections: [],
        change_summary: '补充抽样策略',
        source: 'user_edit',
      },
    }))
  })

  it('serializes Markdown and the complete machine-readable manifest from one export response', () => {
    const exported = {
      filename: 'research-delivery.md',
      markdown: '# 正式研究框架',
      manifest: { schema_version: 'research-delivery-v2', evidence: [{ claim: '关键判断' }] },
    }

    expect(serializeM5ResearchExport(exported, 'markdown')).toEqual({
      filename: 'research-delivery.md',
      mediaType: 'text/markdown;charset=utf-8',
      content: '# 正式研究框架',
    })
    expect(serializeM5ResearchExport(exported, 'json')).toEqual({
      filename: 'research-delivery.json',
      mediaType: 'application/json;charset=utf-8',
      content: JSON.stringify(exported.manifest, null, 2),
    })
  })
})
