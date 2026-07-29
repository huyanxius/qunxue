import { useQuery } from '@tanstack/react-query'

import { getResearchTaskViaApi } from './researchTaskApi'

export function useResearchTask(taskId: string) {
  return useQuery({
    queryKey: ['research-task', taskId],
    queryFn: () => getResearchTaskViaApi(taskId),
    enabled: Boolean(taskId),
  })
}
