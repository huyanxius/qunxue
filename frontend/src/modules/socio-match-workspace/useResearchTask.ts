import { useQuery } from '@tanstack/react-query'

import { getResearchTask } from './researchTaskApi'

export function useResearchTask(taskId: string) {
  return useQuery({
    queryKey: ['research-task', taskId],
    queryFn: () => getResearchTask(taskId),
    enabled: Boolean(taskId),
  })
}
