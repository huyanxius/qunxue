/**
 * SocioMatch 的界面无关流程由后端状态控制；本模块只呈现状态并采集用户动作。
 */
export { SocioMatchWorkspace } from './SocioMatchWorkspace'
export type { SocioMatchWorkspaceProps } from './SocioMatchWorkspace'
export { startResearchTask } from './researchTaskActions'
export type {
  ResearchTask,
  ResearchTaskAction,
  ResearchTaskEntryType,
  ResearchTaskStatus,
} from './researchTaskModel'
