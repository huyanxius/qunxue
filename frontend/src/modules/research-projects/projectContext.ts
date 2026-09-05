import { listResearchProjects as listProjects } from './projectApi'

export type ResearchProject = {
  task_id: string
  project_title: string
  status: string
}

export function listResearchProjects(signal?: AbortSignal): Promise<ResearchProject[]> {
  return listProjects(signal)
}

export function groupProjectConversations<
  P extends { task_id: string; project_title: string },
  C extends { conversation_id: string; task_id?: string | null },
>(projects: P[], conversations: C[]) {
  const byProject = new Map(projects.map((project) => [project.task_id, { project, conversations: [] as C[] }]))
  const unassigned: C[] = []
  const unavailable: C[] = []
  for (const conversation of conversations) {
    if (!conversation.task_id) unassigned.push(conversation)
    else {
      const group = byProject.get(conversation.task_id)
      if (group) group.conversations.push(conversation)
      else unavailable.push(conversation)
    }
  }
  return { projects: [...byProject.values()], unassigned, unavailable }
}
