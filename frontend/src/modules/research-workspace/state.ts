import type { AgentToolTrace } from '../research-agent'
import type {
  ArtifactAction,
  ArtifactActionInput,
  ArtifactActionResult,
  ArtifactDocument,
  CanvasAction,
  CanvasActionInput,
  CanvasState,
  ContextRailState,
  ResearchWorkspaceRoute,
  ResearchWorkspaceState,
  WorkspaceActionStatus,
  WorkspaceRunEvent,
  WorkspaceRunState,
} from './types'

const emptyRail: ContextRailState = {
  open: false,
  activeTab: 'agent',
  unreadActivity: 0,
}

const emptyCanvas: CanvasState = {
  nodes: [],
  edges: [],
  selectedNodeId: null,
  focusedNodeId: null,
}

const emptyRun: WorkspaceRunState = {
  runId: null,
  status: 'idle',
  activeActionId: null,
  completedActions: 0,
  totalActions: null,
  lastError: null,
}

function decodeSegment(segment: string): string {
  try {
    return decodeURIComponent(segment)
  } catch {
    return segment
  }
}

/**
 * Resolve only the product's route contract. Router parsing stays in the app
 * shell; this function is deliberately safe for malformed or future paths.
 */
export function routeModeFromPathname(pathname: string): ResearchWorkspaceRoute {
  const segments = pathname.split('/').filter(Boolean).map(decodeSegment)
  if (segments[0] === 'agent') {
    return { mode: 'agent', researchId: null, artifactId: null }
  }
  if (segments[0] === 'research' && segments[1]) {
    if (segments[2] === 'artifacts' && segments[3]) {
      return {
        mode: 'artifact',
        researchId: segments[1],
        artifactId: segments[3],
      }
    }
    return { mode: 'research', researchId: segments[1], artifactId: null }
  }
  return { mode: 'agent', researchId: null, artifactId: null }
}

export function createInitialResearchWorkspaceState(
  route: ResearchWorkspaceRoute = { mode: 'agent', researchId: null, artifactId: null },
): ResearchWorkspaceState {
  return {
    route,
    rail: emptyRail,
    canvas: emptyCanvas,
    artifacts: [],
    run: emptyRun,
    actions: [],
  }
}

export function openContextRail(
  rail: ContextRailState,
  tab: ContextRailState['activeTab'],
): ContextRailState {
  return {
    ...rail,
    open: true,
    activeTab: tab,
    unreadActivity: tab === 'activity' ? 0 : rail.unreadActivity,
  }
}

export function selectContextRailTab(
  rail: ContextRailState,
  tab: ContextRailState['activeTab'],
): ContextRailState {
  return openContextRail(rail, tab)
}

export function closeContextRail(rail: ContextRailState): ContextRailState {
  return { ...rail, open: false }
}

function createActionBase(input: {
  actionId: string
  targetId: string
  beforeVersion: number
  evidence?: readonly { readonly kind: 'knowledge' | 'source' | 'conversation' | 'tool_trace'; readonly id: string }[]
}) {
  return {
    actionId: input.actionId,
    targetId: input.targetId,
    beforeVersion: input.beforeVersion,
    afterVersion: null,
    status: 'pending' as const,
    reversible: true,
    undoActionId: null,
    evidence: [...(input.evidence ?? [])],
  }
}

export function createCanvasAction(input: CanvasActionInput): CanvasAction {
  return {
    domain: 'canvas',
    ...createActionBase(input),
    kind: input.kind,
    payload: input.payload,
  } as CanvasAction
}

export function createArtifactAction(input: ArtifactActionInput): ArtifactAction {
  return {
    domain: 'artifact',
    ...createActionBase(input),
    kind: input.kind,
    payload: input.payload,
  } as ArtifactAction
}

function isValidRange(start: number, end: number, contentLength: number): boolean {
  return Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end >= start && end <= contentLength
}

function actionWithStatus(
  action: ArtifactAction,
  status: WorkspaceActionStatus,
  afterVersion: number | null = action.afterVersion,
): ArtifactAction {
  return { ...action, status, afterVersion } as ArtifactAction
}

/**
 * Apply only deterministic local text transitions. The server remains the
 * source of truth; `beforeVersion` prevents an agent patch from overwriting a
 * newer artifact revision.
 */
export function applyArtifactAction(
  artifact: ArtifactDocument,
  action: ArtifactAction,
): ArtifactActionResult {
  if (action.targetId !== artifact.artifactId) {
    return {
      ok: false,
      reason: 'target_mismatch',
      artifact,
      action: actionWithStatus(action, 'failed', null),
    }
  }
  if (action.beforeVersion !== artifact.version) {
    return {
      ok: false,
      reason: 'stale_version',
      artifact,
      action: actionWithStatus(action, 'failed', null),
    }
  }

  let content = artifact.content
  let mutatesContent = false
  if (action.kind === 'rewrite_selection' || action.kind === 'apply_text_patch') {
    const { start, end, replacement } = action.payload
    if (!isValidRange(start, end, content.length)) {
      return {
        ok: false,
        reason: 'invalid_range',
        artifact,
        action: actionWithStatus(action, 'failed', null),
      }
    }
    content = `${content.slice(0, start)}${replacement}${content.slice(end)}`
    mutatesContent = true
  } else if (action.kind === 'insert_section') {
    const { at, heading, content: sectionContent } = action.payload
    if (!isValidRange(at, at, content.length)) {
      return {
        ok: false,
        reason: 'invalid_range',
        artifact,
        action: actionWithStatus(action, 'failed', null),
      }
    }
    const section = `${heading}\n\n${sectionContent}`
    content = `${content.slice(0, at)}${section}${content.slice(at)}`
    mutatesContent = true
  } else if (action.kind === 'add_citation') {
    const { at, citationId } = action.payload
    if (!isValidRange(at, at, content.length)) {
      return {
        ok: false,
        reason: 'invalid_range',
        artifact,
        action: actionWithStatus(action, 'failed', null),
      }
    }
    content = `${content.slice(0, at)}[${citationId}]${content.slice(at)}`
    mutatesContent = true
  }

  const nextVersion = mutatesContent ? artifact.version + 1 : artifact.version
  return {
    ok: true,
    artifact: {
      ...artifact,
      content,
      version: nextVersion,
    },
    action: actionWithStatus(action, 'succeeded', nextVersion),
  }
}

/**
 * Project a completed canvas command onto the local interaction state. It
 * never invents server data: node and edge payloads must be supplied by the
 * real action response before this projection is used for persistence.
 */
export function applyCanvasAction(canvas: CanvasState, action: CanvasAction): CanvasState {
  if (action.kind === 'select_canvas_node') {
    return { ...canvas, selectedNodeId: action.payload.nodeId }
  }
  if (action.kind === 'focus_canvas_node') {
    return { ...canvas, focusedNodeId: action.payload.nodeId }
  }
  if (action.kind === 'create_canvas_node') {
    if (canvas.nodes.some((node) => node.nodeId === action.payload.nodeId)) return canvas
    return {
      ...canvas,
      nodes: [
        ...canvas.nodes,
        {
          nodeId: action.payload.nodeId,
          kind: action.payload.nodeKind,
          title: action.payload.title,
          version: action.afterVersion ?? action.beforeVersion + 1,
          status: 'idle',
        },
      ],
    }
  }
  if (action.kind === 'connect_canvas_nodes') {
    if (canvas.edges.some((edge) => edge.edgeId === action.payload.edgeId)) return canvas
    return {
      ...canvas,
      edges: [
        ...canvas.edges,
        {
          edgeId: action.payload.edgeId,
          sourceNodeId: action.payload.sourceNodeId,
          targetNodeId: action.payload.targetNodeId,
          version: action.afterVersion ?? action.beforeVersion + 1,
        },
      ],
    }
  }

  const status = action.kind === 'run_canvas_node'
    ? 'running'
    : action.kind === 'pause_canvas_run'
      ? 'paused'
      : action.kind === 'retry_canvas_node'
        ? 'running'
        : action.payload.status
  if (action.kind === 'update_canvas_node' && !status && !action.payload.title) return canvas
  return {
    ...canvas,
    nodes: canvas.nodes.map((node) => {
      if (node.nodeId !== action.targetId || node.version !== action.beforeVersion) return node
      return {
        ...node,
        ...(action.kind === 'update_canvas_node' && action.payload.title
          ? { title: action.payload.title }
          : {}),
        ...(status ? { status } : {}),
        version: action.afterVersion ?? node.version + 1,
      }
    }),
  }
}

function updateAction(
  actions: readonly (CanvasAction | ArtifactAction)[],
  actionId: string,
  update: (action: CanvasAction | ArtifactAction) => CanvasAction | ArtifactAction,
): readonly (CanvasAction | ArtifactAction)[] {
  return actions.map((action) => action.actionId === actionId ? update(action) : action)
}

function setActionStatus(
  actions: readonly (CanvasAction | ArtifactAction)[],
  actionId: string,
  status: WorkspaceActionStatus,
  afterVersion: number | null = null,
): readonly (CanvasAction | ArtifactAction)[] {
  return updateAction(actions, actionId, (action) => ({
    ...action,
    status,
    afterVersion,
  }))
}

function markActivity(rail: ContextRailState): ContextRailState {
  if (rail.open && rail.activeTab === 'activity') return rail
  return {
    ...rail,
    open: true,
    activeTab: 'activity',
    unreadActivity: rail.unreadActivity + 1,
  }
}

function markSources(rail: ContextRailState): ContextRailState {
  return {
    ...rail,
    open: true,
    activeTab: 'sources',
    unreadActivity: 0,
  }
}

function runWith(state: ResearchWorkspaceState, run: WorkspaceRunState): ResearchWorkspaceState {
  return { ...state, run }
}

export function applyRunEvent(
  state: ResearchWorkspaceState,
  event: WorkspaceRunEvent,
): ResearchWorkspaceState {
  switch (event.type) {
    case 'run_queued':
      return {
        ...state,
        rail: openContextRail(state.rail, 'activity'),
        run: {
          runId: event.runId,
          status: 'queued',
          activeActionId: event.action.actionId,
          completedActions: 0,
          totalActions: 1,
          lastError: null,
        },
        actions: state.actions.some((action) => action.actionId === event.action.actionId)
          ? state.actions
          : [...state.actions, event.action],
      }
    case 'run_started':
      return runWith(state, {
        ...state.run,
        runId: event.runId,
        status: 'running',
        lastError: null,
      })
    case 'run_paused':
      return runWith(state, { ...state.run, runId: event.runId, status: 'paused' })
    case 'run_resumed':
      return runWith(state, { ...state.run, runId: event.runId, status: 'running' })
    case 'run_completed':
      return {
        ...state,
        rail: markSources(state.rail),
        run: {
          ...state.run,
          runId: event.runId,
          status: 'succeeded',
          activeActionId: null,
          completedActions: state.run.totalActions ?? state.run.completedActions,
          lastError: null,
        },
        actions: state.run.activeActionId
          ? setActionStatus(state.actions, state.run.activeActionId, 'succeeded')
          : state.actions,
      }
    case 'run_failed':
      return {
        ...state,
        rail: openContextRail(state.rail, 'activity'),
        run: {
          ...state.run,
          runId: event.runId,
          status: 'failed',
          activeActionId: null,
          lastError: event.message,
        },
      }
    case 'run_cancelled':
      return runWith(state, {
        ...state.run,
        runId: event.runId,
        status: 'cancelled',
        activeActionId: null,
      })
    case 'action_started':
      return {
        ...state,
        rail: markActivity(state.rail),
        run: {
          ...state.run,
          runId: event.runId,
          status: 'running',
          activeActionId: event.actionId,
        },
        actions: setActionStatus(state.actions, event.actionId, 'running'),
      }
    case 'action_succeeded':
      return {
        ...state,
        run: {
          ...state.run,
          runId: event.runId,
          activeActionId: null,
          completedActions: state.run.completedActions + 1,
          lastError: null,
        },
        actions: setActionStatus(state.actions, event.actionId, 'succeeded', event.afterVersion),
      }
    case 'action_failed':
      return {
        ...state,
        rail: markActivity(state.rail),
        run: {
          ...state.run,
          runId: event.runId,
          status: 'failed',
          activeActionId: null,
          lastError: event.message,
        },
        actions: setActionStatus(state.actions, event.actionId, 'failed'),
      }
    case 'tool_started':
      return {
        ...state,
        rail: markActivity(state.rail),
        run: {
          ...state.run,
          runId: event.runId,
          status: 'running',
          activeActionId: event.trace.call_id,
          lastError: null,
        },
      }
    case 'tool_finished':
      return runWith(state, {
        ...state.run,
        runId: event.runId,
        status: 'running',
        activeActionId: state.run.activeActionId === event.trace.call_id ? null : state.run.activeActionId,
      })
    case 'tool_failed':
      return {
        ...state,
        rail: markActivity(state.rail),
        run: {
          ...state.run,
          runId: event.runId,
          status: 'running',
          activeActionId: null,
          lastError: event.trace.error ?? event.trace.detail ?? '工具调用失败',
        },
      }
  }
}

/** Convert the real Agent tool trace into the workspace run event contract. */
export function runEventFromAgentToolTrace(
  runId: string,
  trace: AgentToolTrace,
): WorkspaceRunEvent {
  if (trace.phase === 'started') return { type: 'tool_started', runId, trace }
  if (trace.phase === 'finished') return { type: 'tool_finished', runId, trace }
  return { type: 'tool_failed', runId, trace }
}
