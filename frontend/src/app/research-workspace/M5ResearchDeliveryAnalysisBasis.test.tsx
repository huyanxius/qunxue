import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { M5ResearchDeliveryPanel } from './M5ResearchDeliveryPanel'

afterEach(cleanup)

it('keeps the material analysis basis visible beside version and completion controls', () => {
  render(
    <div className="research-document-workbench" data-stage="framework">
      <M5ResearchDeliveryPanel
        state={{
          taskId: 'task-1',
          confirmedTheoryPlanId: 'plan-1',
          phase: 'editing',
          document: {
            analysisBasis: {
              contentHash: 'sha256:abc123',
              codes: [{ id: 'code-1', label: '制度支持', definition: '学校提供的正式资源。' }],
              memos: [],
              comparisons: [],
              unavailableAnnotationCount: 0,
            },
            actor: 'user',
            changeSummary: '接受分析结果',
            confirmedAt: null,
            createdAt: '2026-08-30T00:00:00Z',
            documentId: 'document-1',
            knowledgeReleaseId: 'release-1',
            restoredFromVersion: null,
            revisionId: 'revision-1',
            sections: [],
            status: 'draft',
            taskId: 'task-1',
            theoryPlanId: 'plan-1',
            title: '研究框架',
            version: 2,
          },
          versions: [],
          proposals: [],
          completion: {
            documentId: 'document-1',
            version: 2,
            ready: false,
            completed: false,
            pendingProposalCount: 0,
            blockers: ['仍有章节待审阅'],
            checks: [],
          },
        }}
        theoryPlanLabel="已确认方案 · plan-1"
        saveState="saved"
        createIdempotencyKey={() => 'm5-1'}
        onGenerate={vi.fn(async () => undefined)}
        onAcceptProposal={vi.fn(async () => undefined)}
        onRejectProposal={vi.fn(async () => undefined)}
        onRestoreVersion={vi.fn(async () => undefined)}
        onConfirm={vi.fn(async () => undefined)}
        onExport={vi.fn(async () => undefined)}
      />
    </div>,
  )

  expect(screen.getByRole('region', { name: '本版材料分析依据' })).toHaveTextContent('制度支持')
  expect(screen.getByRole('heading', { name: '可恢复历史' })).toBeVisible()
  expect(screen.getByText('仍有章节待审阅')).toBeVisible()
})
