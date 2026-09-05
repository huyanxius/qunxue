import type { ResearchCentralTool } from '../../modules/socio-match-workspace'

export type ResearchWorkspaceTool =
  | 'map'
  | 'materials'
  | 'analysis'
  | 'theory'
  | 'method'
  | 'writing'
  | 'archive'

export type ResearchWorkspacePosition = Readonly<{
  materialId?: string | null
  parseId?: string | null
  segmentId?: string | null
  documentId?: string | null
  sectionId?: string | null
  version?: number | null
}>

const centralToolDestinations: Record<ResearchCentralTool, ResearchWorkspaceTool> = {
  agent: 'map',
  research_map: 'map',
  materials: 'materials',
  phenomenon: 'map',
  theory_matching: 'theory',
  framework: 'writing',
  method: 'method',
}

const legacyStageDestinations: Readonly<Record<string, ResearchWorkspaceTool>> = {
  phenomenon: 'map',
  match: 'theory',
  framework: 'writing',
  method: 'method',
}

const workspaceTools = new Set<ResearchWorkspaceTool>([
  'map',
  'materials',
  'analysis',
  'theory',
  'method',
  'writing',
  'archive',
])

const RESUME_STORAGE_PREFIX = 'qunxue.research-workspace.resume.v1:'

type WorkspaceStorage = Pick<Storage, 'getItem' | 'setItem'>

function decodePathSegment(value: string) {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

export function researchWorkspaceToolFromProject(
  centralTool: ResearchCentralTool | string | null | undefined,
): ResearchWorkspaceTool {
  return centralTool && centralTool in centralToolDestinations
    ? centralToolDestinations[centralTool as ResearchCentralTool]
    : 'map'
}

export function researchWorkspaceDestination(
  taskId: string,
  tool: ResearchWorkspaceTool,
  position: ResearchWorkspacePosition = {},
) {
  const search = new URLSearchParams()
  if (position.materialId) search.set('material_id', position.materialId)
  if (position.parseId) search.set('parse_id', position.parseId)
  if (position.segmentId) search.set('segment_id', position.segmentId)
  if (position.documentId) search.set('document_id', position.documentId)
  if (position.sectionId) search.set('section_id', position.sectionId)
  if (position.version != null) search.set('version', String(position.version))
  const query = search.toString()
  return `/research/${encodeURIComponent(taskId)}/workspace/${tool}${query ? `?${query}` : ''}`
}

function isWorkspacePathForTask(taskId: string, value: string) {
  const url = new URL(value, 'https://qunxue.local')
  const match = url.pathname.match(/^\/research\/([^/]+)\/workspace\/([^/]+)$/)
  return Boolean(
    match
    && decodePathSegment(match[1] ?? '') === taskId
    && workspaceTools.has((match[2] ?? '') as ResearchWorkspaceTool),
  )
}

export function rememberResearchWorkspaceResumePath(
  taskId: string,
  path: string,
  storage: WorkspaceStorage = window.localStorage,
) {
  if (!isWorkspacePathForTask(taskId, path)) return
  try {
    storage.setItem(`${RESUME_STORAGE_PREFIX}${taskId}`, path)
  } catch {
    // The URL remains the recovery source when storage is unavailable.
  }
}

export function readResearchWorkspaceResumePath(
  taskId: string,
  storage: Pick<Storage, 'getItem'> = window.localStorage,
) {
  try {
    const path = storage.getItem(`${RESUME_STORAGE_PREFIX}${taskId}`)
    return path && isWorkspacePathForTask(taskId, path) ? path : null
  } catch {
    return null
  }
}

export function legacyResearchWorkspaceDestination(value: string): string | null {
  const url = new URL(value, 'https://qunxue.local')
  if (url.pathname === '/research/materials') {
    const taskId = url.searchParams.get('task_id')
    if (!taskId || !url.searchParams.get('material_id')) return null
    url.searchParams.delete('task_id')
    const query = url.searchParams.toString()
    return `${researchWorkspaceDestination(taskId, 'materials')}${query ? `?${query}` : ''}${url.hash}`
  }

  const match = url.pathname.match(/^\/research\/([^/]+)\/(phenomenon|match|framework|method)$/)
  if (!match) return null
  const [, encodedTaskId = '', stage = ''] = match
  const tool = legacyStageDestinations[stage]
  if (!tool) return null
  return `${researchWorkspaceDestination(decodePathSegment(encodedTaskId), tool)}${url.search}${url.hash}`
}
