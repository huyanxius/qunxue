import { createResearchTaskViaApi } from './researchTaskApi'
import type { ResearchTask } from './researchTaskModel'

export function createMaterialFirstResearchProject(
  requestKey: string,
  projectTitle: string,
): Promise<ResearchTask> {
  return createResearchTaskViaApi(requestKey, {
    entryType: 'material_input',
    entryMode: 'from_scratch',
    projectTitle,
  })
}

export function createExistingResearchProject(
  requestKey: string,
  values: {
    projectTitle: string
    projectStage: string
    methodOrientation?: string
  },
): Promise<ResearchTask> {
  return createResearchTaskViaApi(requestKey, {
    entryType: 'material_input',
    entryMode: 'existing_research',
    ...values,
  })
}
