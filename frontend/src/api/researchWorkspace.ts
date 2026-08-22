import { apiClient } from './client'
import { ApiRequestError } from './error'
import {
  acceptResearchDocumentProposal as acceptResearchDocumentProposalRequest,
  acknowledgePartialMatch as acknowledgePartialMatchRequest,
  confirmResearchDocument as confirmResearchDocumentRequest,
  confirmTheoryPlan as confirmTheoryPlanRequest,
  createMatchRun as createMatchRunRequest,
  createTheoryDecisions as createTheoryDecisionsRequest,
  exportResearchDocument as exportResearchDocumentRequest,
  getMatchRun as getMatchRunRequest,
  getResearchTaskNavigation as getResearchTaskNavigationRequest,
  listResearchDocuments as listResearchDocumentsRequest,
  listResearchDocumentVersions as listResearchDocumentVersionsRequest,
  listResearchTaskDocumentProposals as listResearchTaskDocumentProposalsRequest,
  listTheoryDecisions as listTheoryDecisionsRequest,
  rejectResearchDocumentProposal as rejectResearchDocumentProposalRequest,
  restoreResearchDocument as restoreResearchDocumentRequest,
  updateResearchDocument as updateResearchDocumentRequest,
} from './generated'

function withClient<T extends { client?: unknown }>(options: T): T {
  return { ...options, client: apiClient }
}

export async function acceptResearchDocumentProposal(
  options: Parameters<typeof acceptResearchDocumentProposalRequest>[0],
) {
  return await acceptResearchDocumentProposalRequest(withClient(options))
}

export async function acknowledgePartialMatch(
  options: Parameters<typeof acknowledgePartialMatchRequest>[0],
) {
  return await acknowledgePartialMatchRequest(withClient(options))
}

export async function confirmResearchDocument(
  options: Parameters<typeof confirmResearchDocumentRequest>[0],
) {
  return await confirmResearchDocumentRequest(withClient(options))
}

export async function confirmTheoryPlan(
  options: Parameters<typeof confirmTheoryPlanRequest>[0],
) {
  return await confirmTheoryPlanRequest(withClient(options))
}

export async function createMatchRun(
  options: Parameters<typeof createMatchRunRequest>[0],
) {
  return await createMatchRunRequest(withClient(options))
}

export async function createTheoryDecisions(
  options: Parameters<typeof createTheoryDecisionsRequest>[0],
) {
  return await createTheoryDecisionsRequest(withClient(options))
}

export async function exportResearchDocument(
  options: Parameters<typeof exportResearchDocumentRequest>[0],
) {
  return await exportResearchDocumentRequest(withClient(options))
}

export async function getMatchRun(options: Parameters<typeof getMatchRunRequest>[0]) {
  return await getMatchRunRequest(withClient(options))
}

export async function getResearchTaskNavigation(
  options: Parameters<typeof getResearchTaskNavigationRequest>[0],
) {
  return await getResearchTaskNavigationRequest(withClient(options))
}

export async function readResearchTaskNavigationViaApi(
  taskId: string,
) {
  const { data, response } = await getResearchTaskNavigationRequest({
    client: apiClient,
    path: { task_id: taskId },
  })
  if (!data) {
    throw new ApiRequestError('研究进度读取失败。', response?.status)
  }
  return data
}

export async function listResearchDocuments(
  options: Parameters<typeof listResearchDocumentsRequest>[0],
) {
  return await listResearchDocumentsRequest(withClient(options))
}

export async function listResearchDocumentVersions(
  options: Parameters<typeof listResearchDocumentVersionsRequest>[0],
) {
  return await listResearchDocumentVersionsRequest(withClient(options))
}

export async function listResearchTaskDocumentProposals(
  options: Parameters<typeof listResearchTaskDocumentProposalsRequest>[0],
) {
  return await listResearchTaskDocumentProposalsRequest(withClient(options))
}

export async function listTheoryDecisions(
  options: Parameters<typeof listTheoryDecisionsRequest>[0],
) {
  return await listTheoryDecisionsRequest(withClient(options))
}

export async function rejectResearchDocumentProposal(
  options: Parameters<typeof rejectResearchDocumentProposalRequest>[0],
) {
  return await rejectResearchDocumentProposalRequest(withClient(options))
}

export async function restoreResearchDocument(
  options: Parameters<typeof restoreResearchDocumentRequest>[0],
) {
  return await restoreResearchDocumentRequest(withClient(options))
}

export async function updateResearchDocument(
  options: Parameters<typeof updateResearchDocumentRequest>[0],
) {
  return await updateResearchDocumentRequest(withClient(options))
}
