import type {
  ResearchTask,
  ResearchTaskSubmission,
} from './researchTaskModel'
import { submitResearchTaskViaApi } from './researchTaskApi'

export function submitResearchTask(
  input: ResearchTaskSubmission,
): Promise<ResearchTask> {
  return submitResearchTaskViaApi(input)
}
