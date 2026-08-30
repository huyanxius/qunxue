import { listMyResearchViaApi as listMyResearch } from './accountApi'
import type { MyResearchItem } from './types'

/** Public account facade for pages that need a user's research choices. */
export async function listMyResearchViaApi(): Promise<MyResearchItem[]> {
  return listMyResearch()
}
