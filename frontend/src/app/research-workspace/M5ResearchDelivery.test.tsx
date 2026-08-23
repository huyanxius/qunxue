import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { M5CompletionGate } from './M5CompletionGate'
import { M5ExportPanel } from './M5ExportPanel'
import { M5GenerationState } from './M5GenerationState'
import { M5ProposalReview } from './M5ProposalReview'
import { M5ResearchDeliveryPanel } from './M5ResearchDeliveryPanel'
import { M5VersionHistory } from './M5VersionHistory'

afterEach(cleanup)

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((success, failure) => {
    resolve = success
    reject = failure
  })
  return { promise, resolve, reject }
}

describe('M5 research delivery controls', () => {
  it('explains completion blockers and never confirms an unsaved document', () => {
    const confirm = vi.fn()
    render(
      <M5CompletionGate
        gate={{
          ready: false,
          checks: [
            { code: 'required_sections_reviewed', label: '规定章节已审阅', passed: false, detail: '研究方法仍是草稿' },
            { code: 'pending_proposals_resolved', label: 'Agent 建议已处理', passed: false, detail: '还有 2 条待处理' },
          ],
          blockers: ['研究方法仍是草稿', '还有 2 条待处理'],
        }}
        saveState="unsaved"
        onConfirm={confirm}
      />,
    )

    expect(screen.getByText('研究方法仍是草稿')).toBeVisible()
    expect(screen.getByText('还有 2 条待处理')).toBeVisible()
    const button = screen.getByRole('button', { name: '完成研究' })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(confirm).not.toHaveBeenCalled()
    expect(screen.getByText('请先保存当前修改，再检查完成条件。')).toBeVisible()
  })

  it('shows proposal before/after and locks accept and reject while deciding', async () => {
    const accept = deferred<void>()
    const onAccept = vi.fn(() => accept.promise)
    const onReject = vi.fn(async () => undefined)
    render(
      <M5ProposalReview
        proposal={{
          proposalId: 'proposal-1',
          status: 'pending',
          kind: 'revise_section',
          targetLabel: '研究方法',
          before: '以访谈为主。',
          after: '采用半结构访谈，并说明编码流程。',
          rationale: '让方法可复核。',
          provenance: {
            releaseLabel: '知识版本 release-7',
            modelLabel: 'base · model-2026-08',
            agentRunLabel: '运行 run-3',
          },
        }}
        onAccept={onAccept}
        onReject={onReject}
      />,
    )

    const card = screen.getByRole('article', { name: '研究方法修改建议' })
    expect(within(card).getByText('以访谈为主。')).toBeVisible()
    expect(within(card).getByText('采用半结构访谈，并说明编码流程。')).toBeVisible()
    expect(within(card).getByText('知识版本 release-7')).toBeVisible()

    const acceptButton = within(card).getByRole('button', { name: '接受建议' })
    const rejectButton = within(card).getByRole('button', { name: '拒绝建议' })
    fireEvent.click(acceptButton)
    fireEvent.click(acceptButton)
    fireEvent.click(rejectButton)

    expect(onAccept).toHaveBeenCalledTimes(1)
    expect(onReject).not.toHaveBeenCalled()
    expect(acceptButton).toBeDisabled()
    expect(rejectButton).toBeDisabled()
    accept.resolve()
    await waitFor(() => expect(screen.getByText('建议已接受，正式文档已生成新版本。')).toBeVisible())
  })

  it('records a rejection reason and leaves the proposal retryable after failure', async () => {
    const reject = vi.fn(async () => { throw new Error('决定未写入，请重试') })
    render(
      <M5ProposalReview
        proposal={{
          proposalId: 'proposal-2',
          status: 'pending',
          kind: 'revise_section',
          targetLabel: '伦理风险',
          before: '已取得知情同意。',
          after: '补充撤回机制与匿名化流程。',
          rationale: '披露参与者保护措施。',
          provenance: {
            releaseLabel: '知识版本 release-7',
            modelLabel: 'base · model-2026-08',
            agentRunLabel: '运行 run-4',
          },
        }}
        onAccept={vi.fn(async () => undefined)}
        onReject={reject}
      />,
    )

    const rejectButton = screen.getByRole('button', { name: '拒绝建议' })
    const reason = screen.getByRole('textbox', { name: '拒绝理由（必填，将写入审阅记录）' })
    expect(reason).toBeRequired()
    expect(rejectButton).toBeDisabled()

    fireEvent.change(reason, {
      target: { value: '该建议超出研究对象授权范围。' },
    })
    expect(rejectButton).toBeEnabled()
    fireEvent.click(rejectButton)

    expect(await screen.findByText('决定未写入，请重试')).toBeVisible()
    expect(reject).toHaveBeenCalledWith('proposal-2', '该建议超出研究对象授权范围。')
    expect(rejectButton).toBeEnabled()
  })

  it('keeps a failed generation request available for an exact retry', async () => {
    const calls: Array<{ idempotencyKey: string; prompt: string }> = []
    const run = vi.fn(async (attempt: { idempotencyKey: string; prompt: string }) => {
      calls.push(attempt)
      if (calls.length === 1) throw new Error('网络已断开')
    })
    render(
      <M5GenerationState
        theoryPlanLabel="已确认方案 · plan-7"
        createIdempotencyKey={() => 'm5-generate-1'}
        onGenerate={run}
      />,
    )

    const generate = screen.getByRole('button', { name: '生成研究框架草稿' })
    fireEvent.click(generate)
    fireEvent.click(generate)
    await screen.findByText('网络已断开')
    expect(run).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: '重试原请求' }))
    await waitFor(() => expect(run).toHaveBeenCalledTimes(2))
    expect(calls[1]).toEqual(calls[0])
    expect(await screen.findByText('草稿已生成，等待你逐条审阅建议。')).toBeVisible()
  })

  it('reports version restore failures without changing the selected version', async () => {
    const restore = vi.fn(async () => { throw new Error('版本已被其他设备更新') })
    render(
      <M5VersionHistory
        currentVersion={4}
        versions={[
          { version: 4, createdAt: '2026-08-22T10:00:00Z', actorLabel: '你', summary: '补充伦理说明', status: 'draft' },
          { version: 3, createdAt: '2026-08-22T09:00:00Z', actorLabel: '你', summary: '调整研究方法', status: 'draft' },
        ]}
        onRestore={restore}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '恢复第 3 版' }))
    expect(await screen.findByText('版本已被其他设备更新')).toBeVisible()
    expect(screen.getByText('当前版本')).toBeVisible()
  })

  it('keeps export unavailable until the confirmed package is ready and reports download results', async () => {
    const exportPackage = vi.fn(async (format: 'markdown' | 'json') => {
      if (format === 'json') throw new Error('导出服务暂时不可用')
    })
    const { rerender } = render(
      <M5ExportPanel
        confirmed={false}
        gateReady={false}
        saveState="saved"
        onExport={exportPackage}
      />,
    )

    expect(screen.getByRole('button', { name: '下载 Markdown' })).toBeDisabled()
    expect(screen.getByText('研究完成并通过门禁后，才会生成可审查的成果包。')).toBeVisible()

    rerender(
      <M5ExportPanel
        confirmed
        gateReady
        saveState="saved"
        onExport={exportPackage}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '下载 Markdown' }))
    await waitFor(() => expect(screen.getByText('Markdown 成果包已下载。')).toBeVisible())
    fireEvent.click(screen.getByRole('button', { name: '下载 JSON' }))
    expect(await screen.findByText('导出服务暂时不可用')).toBeVisible()
  })

  it('projects persisted proposal and model provenance through the independent M5 panel', () => {
    render(
      <div className="research-document-workbench" data-stage="framework">
        <M5ResearchDeliveryPanel
          state={{
            taskId: 'task-7',
            confirmedTheoryPlanId: 'plan-7',
            phase: 'awaiting_review',
            document: null,
            versions: [],
            proposals: [{
              proposalId: 'proposal-7',
              agentRunId: 'run-7',
              modelProvider: 'openai-compatible',
              modelName: 'research-model-v1',
              baseDocumentVersion: null,
              conversationId: 'conversation-7',
              createdAt: '2026-08-22T10:00:00Z',
              decidedAt: null,
              decisionReason: null,
              documentId: null,
              kind: 'create',
              knowledgeReleaseId: 'release-7',
              proposedSections: [{
                sectionId: 'research_question',
                key: 'research_question',
                title: '研究问题',
                content: '成员流动如何改变社区互助？',
                status: 'reviewed',
                evidenceRefs: [],
              }],
              rationale: '基于已确认理论方案生成。',
              requiresUserApproval: true,
              resultDocumentId: null,
              resultDocumentVersion: null,
              status: 'pending',
              targetSectionId: null,
              taskId: 'task-7',
              theoryPlanId: 'plan-7',
              title: '社区互助研究框架',
              userId: 'user-7',
            }],
            completion: {
              documentId: null,
              version: null,
              ready: false,
              completed: false,
              pendingProposalCount: 1,
              blockers: ['请先审批待处理的 Agent 建议。'],
              checks: [],
            },
          }}
          theoryPlanLabel="已确认方案 · plan-7"
          saveState="saved"
          createIdempotencyKey={() => 'generate-7'}
          onGenerate={vi.fn(async () => undefined)}
          onAcceptProposal={vi.fn(async () => undefined)}
          onRejectProposal={vi.fn(async () => undefined)}
          onRestoreVersion={vi.fn(async () => undefined)}
          onConfirm={vi.fn(async () => undefined)}
          onExport={vi.fn(async () => undefined)}
        />
      </div>,
    )

    expect(screen.getByText('正式研究框架草稿 · 1/12 个章节')).toBeVisible()
    expect(screen.getByText('openai-compatible · research-model-v1')).toBeVisible()
    expect(screen.getByText('知识版本 release-7')).toBeVisible()
    expect(screen.queryByRole('button', { name: '生成研究框架草稿' })).not.toBeInTheDocument()
  })
})
