import { uploadResearchMaterial } from './researchMaterialsApi'

/**
 * Entry pages hand the first batch to the existing task-scoped material system.
 * Keeping the loop here prevents app routes from depending on its transport adapter.
 */
export async function uploadInitialResearchMaterials(
  taskId: string,
  files: readonly File[],
): Promise<void> {
  for (const file of files) await uploadResearchMaterial(taskId, file, 'other')
}
