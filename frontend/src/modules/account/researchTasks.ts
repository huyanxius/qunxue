import { useQuery } from '@tanstack/react-query'

import { usePrivateQueryKey } from '../../query/privateQueryKey'
import { listMyResearchViaApi as listMyResearch } from './accountApi'
import type { MyResearchItem } from './types'

/** Public account facade for pages that need a user's research choices. */
export async function listMyResearchViaApi(): Promise<MyResearchItem[]> {
  return listMyResearch()
}

export function useMyResearchQuery() {
  const queryKey = usePrivateQueryKey('research-tasks')
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => listMyResearch(signal),
    retry: false,
    refetchOnMount: 'always',
  })
  return { queryKey, query }
}
