export {
  applyArtifactAction,
  applyCanvasAction,
  applyRunEvent,
  closeContextRail,
  createArtifactAction,
  createCanvasAction,
  createInitialResearchWorkspaceState,
  openContextRail,
  routeModeFromPathname,
  runEventFromAgentToolTrace,
  selectContextRailTab,
} from './state'

export {
  createEmptyResearchCanvasProjection,
  projectResearchCanvas,
} from './researchCanvasProjection'

export { projectFormalResearchCanvas } from './formalResearchCanvasProjection'

export type { FormalResearchCanvasInput } from './formalResearchCanvasProjection'

export type {
  ResearchCanvasEdge,
  ResearchCanvasNode,
  ResearchCanvasNodeKind,
  ResearchCanvasNodeStatus,
  ResearchCanvasProjection,
  ResearchCanvasStatus,
  ResearchCanvasStreamingTurn,
} from './researchCanvasProjection'

export type {
  ArtifactAction,
  ArtifactActionInput,
  ArtifactActionResult,
  ArtifactDocument,
  ArtifactKind,
  CanvasAction,
  CanvasActionInput,
  CanvasEdge,
  CanvasNode,
  CanvasNodeKind,
  CanvasNodeStatus,
  CanvasState,
  ContextRailState,
  ContextRailTab,
  ResearchWorkspaceRoute,
  ResearchWorkspaceRouteMode,
  ResearchWorkspaceState,
  WorkspaceActionBase,
  WorkspaceActionStatus,
  WorkspaceEvidenceRef,
  WorkspaceRunEvent,
  WorkspaceRunState,
  WorkspaceRunStatus,
} from './types'
export { composeResearchDiscussion, latestResearchAsk, resolveResearchCitation, collapseDocumentNodes } from './researchCollaboration'
export type { ResearchDiscussion, ResearchAsk } from './researchCollaboration'
export { arrangeResearchCanvas, researchCanvasStages, CANVAS_CARD_SIZE, CANVAS_COLUMN_GAP } from './researchCanvasLayout'
