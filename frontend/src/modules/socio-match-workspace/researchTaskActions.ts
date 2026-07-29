import type { ResearchTask } from './researchTaskModel'
import { createResearchTaskViaApi } from './researchTaskApi'

/**
 * Public product command for opening a restorable task. HTTP details remain in
 * the module adapter and are not part of the public module contract.
 */
export function startResearchTask(
  idempotencyKey: string,
): Promise<ResearchTask> {
  return createResearchTaskViaApi(idempotencyKey)
}
