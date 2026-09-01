import { getResearchCycleSnapshot as getResearchCycleSnapshotFromApi } from './researchAnalysisApi'
import type { ResearchCycleSnapshot } from './researchCycleModel'

/** Public facade exposes the loop projection without leaking the transport adapter. */
export async function getResearchCycleSnapshot(
  taskId: string,
  signal?: AbortSignal,
): Promise<ResearchCycleSnapshot> {
  return getResearchCycleSnapshotFromApi(taskId, signal)
}
