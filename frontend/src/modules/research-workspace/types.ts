import type { AgentToolTrace } from '../research-agent'

/**
 * The route decides which surface owns the viewport. It intentionally does
 * not encode React components or router objects, so the same contract can be
 * used by the app shell and by deep-link restoration.
 */
export type ResearchWorkspaceRouteMode = 'agent' | 'research' | 'artifact'

export interface ResearchWorkspaceRoute {
  readonly mode: ResearchWorkspaceRouteMode
  readonly researchId: string | null
  readonly artifactId: string | null
}

export type ContextRailTab = 'agent' | 'activity' | 'sources' | 'basis'

export interface ContextRailState {
  readonly open: boolean
  readonly activeTab: ContextRailTab
  readonly unreadActivity: number
}

export type CanvasNodeKind =
  | 'question'
  | 'evidence'
  | 'theory'
  | 'method'
  | 'claim'
  | 'artifact'
  | 'source'

export type CanvasNodeStatus = 'idle' | 'running' | 'paused' | 'succeeded' | 'failed'

export interface CanvasNode {
  readonly nodeId: string
  readonly kind: CanvasNodeKind
  readonly title: string
  readonly version: number
  readonly status: CanvasNodeStatus
}

export interface CanvasEdge {
  readonly edgeId: string
  readonly sourceNodeId: string
  readonly targetNodeId: string
  readonly version: number
}

export interface CanvasState {
  readonly nodes: readonly CanvasNode[]
  readonly edges: readonly CanvasEdge[]
  readonly selectedNodeId: string | null
  readonly focusedNodeId: string | null
}

export type ArtifactKind = 'question' | 'outline' | 'draft' | 'notes' | 'comparison'

export interface ArtifactDocument {
  readonly artifactId: string
  readonly kind: ArtifactKind
  readonly title: string
  readonly content: string
  readonly version: number
  readonly updatedAt: string
}

export type WorkspaceActionStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'undone'

export interface WorkspaceEvidenceRef {
  readonly kind: 'knowledge' | 'source' | 'conversation' | 'tool_trace'
  readonly id: string
}

export interface WorkspaceActionBase {
  readonly actionId: string
  readonly targetId: string
  readonly beforeVersion: number
  readonly afterVersion: number | null
  readonly status: WorkspaceActionStatus
  readonly reversible: boolean
  readonly undoActionId: string | null
  readonly evidence: readonly WorkspaceEvidenceRef[]
}

export type CanvasAction =
  | (WorkspaceActionBase & {
      readonly domain: 'canvas'
      readonly kind: 'select_canvas_node'
      readonly payload: { readonly nodeId: string }
    })
  | (WorkspaceActionBase & {
      readonly domain: 'canvas'
      readonly kind: 'focus_canvas_node'
      readonly payload: { readonly nodeId: string }
    })
  | (WorkspaceActionBase & {
      readonly domain: 'canvas'
      readonly kind: 'create_canvas_node'
      readonly payload: {
        readonly nodeId: string
        readonly nodeKind: CanvasNodeKind
        readonly title: string
      }
    })
  | (WorkspaceActionBase & {
      readonly domain: 'canvas'
      readonly kind: 'update_canvas_node'
      readonly payload: { readonly title?: string; readonly status?: CanvasNodeStatus }
    })
  | (WorkspaceActionBase & {
      readonly domain: 'canvas'
      readonly kind: 'connect_canvas_nodes'
      readonly payload: {
        readonly edgeId: string
        readonly sourceNodeId: string
        readonly targetNodeId: string
      }
    })
  | (WorkspaceActionBase & {
      readonly domain: 'canvas'
      readonly kind: 'run_canvas_node' | 'pause_canvas_run' | 'retry_canvas_node'
      readonly payload: Record<string, never>
    })

export type CanvasActionInput = {
  readonly actionId: string
  readonly targetId: string
  readonly beforeVersion: number
  readonly evidence?: readonly WorkspaceEvidenceRef[]
} & (
  | {
      readonly kind: 'select_canvas_node' | 'focus_canvas_node'
      readonly payload: { readonly nodeId: string }
    }
  | {
      readonly kind: 'create_canvas_node'
      readonly payload: {
        readonly nodeId: string
        readonly nodeKind: CanvasNodeKind
        readonly title: string
      }
    }
  | {
      readonly kind: 'update_canvas_node'
      readonly payload: { readonly title?: string; readonly status?: CanvasNodeStatus }
    }
  | {
      readonly kind: 'connect_canvas_nodes'
      readonly payload: {
        readonly edgeId: string
        readonly sourceNodeId: string
        readonly targetNodeId: string
      }
    }
  | {
      readonly kind: 'run_canvas_node' | 'pause_canvas_run' | 'retry_canvas_node'
      readonly payload: Record<string, never>
    }
)

export type ArtifactAction =
  | (WorkspaceActionBase & {
      readonly domain: 'artifact'
      readonly kind: 'read_artifact'
      readonly payload: Record<string, never>
    })
  | (WorkspaceActionBase & {
      readonly domain: 'artifact'
      readonly kind: 'rewrite_selection' | 'apply_text_patch'
      readonly payload: { readonly start: number; readonly end: number; readonly replacement: string }
    })
  | (WorkspaceActionBase & {
      readonly domain: 'artifact'
      readonly kind: 'insert_section'
      readonly payload: { readonly at: number; readonly heading: string; readonly content: string }
    })
  | (WorkspaceActionBase & {
      readonly domain: 'artifact'
      readonly kind: 'add_citation'
      readonly payload: { readonly at: number; readonly citationId: string }
    })
  | (WorkspaceActionBase & {
      readonly domain: 'artifact'
      readonly kind: 'compare_versions'
      readonly payload: { readonly compareWithVersion: number }
    })

export type ArtifactActionInput = {
  readonly actionId: string
  readonly targetId: string
  readonly beforeVersion: number
  readonly evidence?: readonly WorkspaceEvidenceRef[]
} & (
  | {
      readonly kind: 'read_artifact'
      readonly payload: Record<string, never>
    }
  | {
      readonly kind: 'rewrite_selection' | 'apply_text_patch'
      readonly payload: { readonly start: number; readonly end: number; readonly replacement: string }
    }
  | {
      readonly kind: 'insert_section'
      readonly payload: { readonly at: number; readonly heading: string; readonly content: string }
    }
  | {
      readonly kind: 'add_citation'
      readonly payload: { readonly at: number; readonly citationId: string }
    }
  | {
      readonly kind: 'compare_versions'
      readonly payload: { readonly compareWithVersion: number }
    }
)

export type WorkspaceRunStatus =
  | 'idle'
  | 'queued'
  | 'running'
  | 'paused'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

export interface WorkspaceRunState {
  readonly runId: string | null
  readonly status: WorkspaceRunStatus
  readonly activeActionId: string | null
  readonly completedActions: number
  readonly totalActions: number | null
  readonly lastError: string | null
}

export type WorkspaceRunEvent =
  | { readonly type: 'run_queued'; readonly runId: string; readonly action: CanvasAction | ArtifactAction }
  | { readonly type: 'run_started'; readonly runId: string }
  | { readonly type: 'run_paused'; readonly runId: string }
  | { readonly type: 'run_resumed'; readonly runId: string }
  | { readonly type: 'run_completed'; readonly runId: string }
  | { readonly type: 'run_failed'; readonly runId: string; readonly message: string }
  | { readonly type: 'run_cancelled'; readonly runId: string }
  | { readonly type: 'action_started'; readonly runId: string; readonly actionId: string }
  | {
      readonly type: 'action_succeeded'
      readonly runId: string
      readonly actionId: string
      readonly afterVersion: number | null
    }
  | {
      readonly type: 'action_failed'
      readonly runId: string
      readonly actionId: string
      readonly message: string
    }
  | { readonly type: 'tool_started'; readonly runId: string; readonly trace: AgentToolTrace }
  | { readonly type: 'tool_finished'; readonly runId: string; readonly trace: AgentToolTrace }
  | { readonly type: 'tool_failed'; readonly runId: string; readonly trace: AgentToolTrace }

export interface ResearchWorkspaceState {
  readonly route: ResearchWorkspaceRoute
  readonly rail: ContextRailState
  readonly canvas: CanvasState
  readonly artifacts: readonly ArtifactDocument[]
  readonly run: WorkspaceRunState
  readonly actions: readonly (CanvasAction | ArtifactAction)[]
}

export type ArtifactActionResult =
  | { readonly ok: true; readonly artifact: ArtifactDocument; readonly action: ArtifactAction }
  | {
      readonly ok: false
      readonly reason: 'stale_version' | 'invalid_range' | 'target_mismatch'
      readonly artifact: ArtifactDocument
      readonly action: ArtifactAction
    }
