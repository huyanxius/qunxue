import { useQuery } from '@tanstack/react-query'

import { usePrivateQueryKey } from '../../query/privateQueryKey'
import { getResearchTaskViaApi } from './researchTaskApi'

export function useResearchTask(taskId: string) {
  return useQuery({
    queryKey: usePrivateQueryKey('research-task', taskId),
    queryFn: ({ signal }) => getResearchTaskViaApi(taskId, signal),
    enabled: Boolean(taskId),
  })
}
