import { apiClient } from '../../api/client'
import { listResearchTasks } from '../../api/generated'
import type { ResearchProject } from './projectContext'

/** All project resources use the existing task ID, including conversations and materials. */
export async function listResearchProjects(signal?: AbortSignal): Promise<ResearchProject[]> {
  const projects: ResearchProject[] = []
  let cursor: string | undefined
  do {
    const { data } = await listResearchTasks({ client: apiClient, signal, query: { limit: 100, cursor } })
    if (!data) throw new Error('项目列表暂时无法加载')
    projects.push(...data.items.map((item) => ({
      task_id: item.task_id, project_title: item.project_title, status: item.status,
    })))
    cursor = data.next_cursor ?? undefined
  } while (cursor)
  return projects
}
