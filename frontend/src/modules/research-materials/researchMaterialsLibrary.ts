import { deleteResearchMaterial, listResearchMaterials, uploadResearchMaterial, listAgentMaterials as listAgentMaterialsRequest, prepareAgentMaterialContext as prepareAgentMaterialContextRequest, getResearchMaterial } from './researchMaterialsApi'

/**
 * 聚合材料页只需要列举、添加和删除普通材料，不应把 HTTP adapter 暴露到模块公共入口。
 * 这里固定上传种类，避免页面层复制材料 API 的传输参数。
 */
export function listResearchLibraryMaterials(taskId: string, signal?: AbortSignal) {
  return listResearchMaterials(taskId, signal)
}

export function addResearchLibraryMaterial(taskId: string, file: File, signal?: AbortSignal) {
  return uploadResearchMaterial(taskId, file, 'other', signal)
}

export function listAgentMaterials(signal?: AbortSignal) {
  return listAgentMaterialsRequest(signal)
}

export function prepareAgentMaterialContext(conversationId: string | null, requestKey: string) {
  return prepareAgentMaterialContextRequest(conversationId, requestKey)
}

export function getAgentAttachmentMaterial(taskId: string, materialId: string) {
  return getResearchMaterial(taskId, materialId)
}

export function removeResearchLibraryMaterial(taskId: string, materialId: string) {
  return deleteResearchMaterial(taskId, materialId)
}
