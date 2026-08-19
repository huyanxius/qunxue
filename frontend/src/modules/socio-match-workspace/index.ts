/**
 * SocioMatch 的界面无关流程由后端状态控制；本模块只呈现状态并采集用户动作。
 */
export { SocioMatchWorkspace } from './SocioMatchWorkspace'
export { NewResearchPage, PhenomenonWorkspace } from './PhenomenonWorkspace'
export { ResearchDemoPreview } from './ResearchDemoPreview'
export { ResearchWorkspaceShell } from './ResearchWorkspaceShell'
export type { ResearchStageId } from './ResearchWorkspaceShell'
export type { SocioMatchWorkspaceProps } from './SocioMatchWorkspace'
export { startResearchTask } from './researchTaskActions'
export type {
  ResearchTask,
  ResearchTaskAction,
  ResearchTaskEntryType,
  ResearchTaskStatus,
} from './researchTaskModel'
