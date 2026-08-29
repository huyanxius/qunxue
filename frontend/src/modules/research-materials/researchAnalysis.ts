import { getAnalysisSnapshot as getAnalysisSnapshotFromApi } from './researchAnalysisApi'
import type { ResearchAnalysisSnapshot } from './researchAnalysisModel'

/** Public module facade keeps app code independent of the transport adapter. */
export async function getAnalysisSnapshot(
  taskId: string,
  signal?: AbortSignal,
): Promise<ResearchAnalysisSnapshot> {
  return getAnalysisSnapshotFromApi(taskId, signal)
}
