import type {
  M5ExportFormat,
  M5ResearchDeliveryState,
} from '../../api/m5ResearchDelivery'
import { M5CompletionGate } from './M5CompletionGate'
import { M5ExportPanel } from './M5ExportPanel'
import { type M5GenerationAttempt, M5GenerationState } from './M5GenerationState'
import { type M5Proposal, M5ProposalReview } from './M5ProposalReview'
import { M5VersionHistory } from './M5VersionHistory'

import './m5-research-delivery.css'

type SaveState = 'saved' | 'saving' | 'unsaved'

type Props = {
  state: M5ResearchDeliveryState
  theoryPlanLabel: string
  saveState: SaveState
  createIdempotencyKey: () => string
  onGenerate: (attempt: M5GenerationAttempt) => Promise<void>
  onAcceptProposal: (proposalId: string) => Promise<void>
  onRejectProposal: (proposalId: string, reason: string) => Promise<void>
  onRestoreVersion: (version: number) => Promise<void>
  onConfirm: () => Promise<void>
  onExport: (format: M5ExportFormat) => Promise<void>
}

function proposalPresentation(
  proposal: M5ResearchDeliveryState['proposals'][number],
  state: M5ResearchDeliveryState,
): M5Proposal {
  const target = proposal.proposedSections[0] ?? null
  const before = proposal.kind === 'revise_section' && target
    ? state.document?.sections.find((section) => section.sectionId === target.sectionId)?.content ?? null
    : null
  const after = proposal.proposedSections
    .map((section) => `${section.title}\n${section.content}`)
    .join('\n\n')
  return {
    proposalId: proposal.proposalId,
    status: proposal.status,
    kind: proposal.kind,
    targetLabel: proposal.kind === 'create'
      ? `正式研究框架草稿 · ${proposal.proposedSections.length}/12 个章节`
      : target?.title ?? proposal.title,
    before,
    after,
    rationale: proposal.rationale,
    decisionReason: proposal.decisionReason,
    provenance: {
      releaseLabel: `知识版本 ${proposal.knowledgeReleaseId}`,
      modelLabel: proposal.modelProvider && proposal.modelName
        ? `${proposal.modelProvider} · ${proposal.modelName}`
        : '旧建议未保留模型标识',
      agentRunLabel: `运行 ${proposal.agentRunId}`,
    },
  }
}

export function M5ResearchDeliveryPanel({
  state,
  theoryPlanLabel,
  saveState,
  createIdempotencyKey,
  onGenerate,
  onAcceptProposal,
  onRejectProposal,
  onRestoreVersion,
  onConfirm,
  onExport,
}: Props) {
  const pendingProposal = state.proposals.some((proposal) => proposal.status === 'pending')
  const versions = state.versions.map((version) => ({
    version: version.version,
    createdAt: version.createdAt,
    actorLabel: version.actor === 'user' ? '你' : 'Agent 建议（已接受）',
    summary: version.changeSummary,
    status: version.status,
    restoredFromVersion: version.restoredFromVersion,
  }))

  return (
    <aside className="m5-delivery-stack" aria-label="M5 研究交付审阅">
      {!state.document && !pendingProposal && (
        <M5GenerationState
          theoryPlanLabel={theoryPlanLabel}
          createIdempotencyKey={createIdempotencyKey}
          onGenerate={onGenerate}
        />
      )}

      {state.proposals.map((proposal) => (
        <M5ProposalReview
          key={proposal.proposalId}
          proposal={proposalPresentation(proposal, state)}
          onAccept={onAcceptProposal}
          onReject={onRejectProposal}
        />
      ))}

      {state.document && (
        <>
          <M5VersionHistory
            currentVersion={state.document.version}
            versions={versions}
            onRestore={onRestoreVersion}
          />
          <M5CompletionGate
            gate={{
              ready: state.completion.ready,
              checks: state.completion.checks,
              blockers: state.completion.blockers,
            }}
            version={state.completion.version}
            completed={state.completion.completed}
            saveState={saveState}
            onConfirm={onConfirm}
          />
          <M5ExportPanel
            confirmed={state.completion.completed}
            gateReady={state.completion.ready}
            saveState={saveState}
            onExport={onExport}
          />
        </>
      )}
    </aside>
  )
}
