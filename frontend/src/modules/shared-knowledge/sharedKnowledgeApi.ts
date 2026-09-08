import { apiClient } from '../../api/client'
import { createMultipartBody } from '../../api/multipart'
import {
  getCourseProfile, updateCourseProfile, organizeSharedDocument,
  listSharedKnowledgeBases, createSharedKnowledgeBase, getSharedKnowledgeBase,
  updateSharedKnowledgeBase, deleteSharedKnowledgeBase, joinSharedKnowledgeBase,
  leaveSharedKnowledgeBase, uploadSharedDocument, detachSharedDocument, getSharedDocumentSource,
  type SharedKnowledgeResponse, type SharedDocumentResponse,
  type CreateSharedKnowledgeRequest, type UpdateSharedKnowledgeRequest,
} from '../../api/generated'

import type { SharedCourse, SharedDocument, SharedSource } from './sharedKnowledgeModel'

function document(value: SharedDocumentResponse): SharedDocument {
  return { id: value.id, filename: value.filename, mediaType: value.media_type,
    sizeBytes: value.size_bytes, parseId: value.parse_id, status: value.status,
    knowledgeStatus: value.knowledge_status ?? 'queued', indexStatus: value.index_status ?? 'queued',
    knowledge: value.knowledge ? { summary: value.knowledge.summary,
      topics: value.knowledge.topics.map((topic) => ({ title: topic.title, summary: topic.summary, segmentIds: topic.segment_ids })),
      relations: (value.knowledge.relations ?? []).map((relation) => ({ source: relation.source, target: relation.target, label: relation.label, segmentIds: relation.segment_ids })),
    } : null, knowledgeError: value.knowledge_error ?? null,
    indexError: value.index_error ?? null,
    errorMessage: value.error_message ?? null, warnings: value.warnings ?? [], createdAt: value.created_at }
}
function course(value: SharedKnowledgeResponse): SharedCourse {
  return { id: value.id, name: value.name ?? null, description: value.description ?? null,
    access: value.viewer_access, sharingEnabled: value.sharing_enabled ?? false,
    shareToken: value.share_token ?? null, readyDocumentCount: value.ready_document_count ?? 0,
    documents: (value.documents ?? []).map(document) }
}
const headers = () => ({ 'Idempotency-Key': crypto.randomUUID() })
function data<T>(result: { data?: T; error?: unknown }): T {
  if (result.error) {
    const error = result.error as { error?: { message?: string } }
    throw new Error(error.error?.message ?? '课程资料暂时无法访问，请重试。')
  }
  if (result.data === undefined) throw new Error('未收到课程数据，请重试。')
  return result.data
}
function checked(result: { error?: unknown }) {
  if (result.error) data(result)
}
export async function listCourses() {
  const items = data(await listSharedKnowledgeBases({ client: apiClient })).items
  if (!Array.isArray(items)) throw new Error('课程列表暂时无法读取。')
  return items.map(course)
}
export async function getCourse(id: string) { return course(data(await getSharedKnowledgeBase({ client: apiClient, path: { kb_id: id } }))) }
export async function createCourse(body: CreateSharedKnowledgeRequest) { return course(data(await createSharedKnowledgeBase({ client: apiClient, body, headers: headers() }))) }
export async function updateCourse(id: string, body: UpdateSharedKnowledgeRequest) { return course(data(await updateSharedKnowledgeBase({ client: apiClient, path: { kb_id: id }, body, headers: headers() }))) }
export async function deleteCourse(id: string) { checked(await deleteSharedKnowledgeBase({ client: apiClient, path: { kb_id: id }, headers: headers() })) }
export async function joinCourse(share_token: string) {
  const value = data(await joinSharedKnowledgeBase({ client: apiClient, body: { share_token }, headers: headers() }))
  return { knowledgeBaseId: value.knowledge_base_id, name: value.name, added: value.added }
}
export async function leaveCourse(id: string) { checked(await leaveSharedKnowledgeBase({ client: apiClient, path: { kb_id: id }, headers: headers() })) }
export async function uploadCourseDocument(id: string, file: File) {
  const multipart = await createMultipartBody([{ name: 'file', file }])
  return document(data(await uploadSharedDocument({ client: apiClient, path: { kb_id: id }, body: { file },
    headers: { ...headers(), 'Content-Type': multipart.contentType }, bodySerializer: () => multipart.body })))
}
export async function detachCourseDocument(id: string, documentId: string) { checked(await detachSharedDocument({ client: apiClient, path: { kb_id: id, document_id: documentId }, headers: headers() })) }
export async function readCourseDocument(id: string, documentId: string, segmentId?: string): Promise<SharedSource> {
  const value = data(await getSharedDocumentSource({ client: apiClient, path: { kb_id: id, document_id: documentId }, query: { segment_id: segmentId } }))
  return { document: document(value.document), knowledgeBaseId: value.knowledge_base_id,
    knowledgeBaseName: value.knowledge_base_name, segments: value.segments.map((item) => ({
      id: item.segment_id, parseId: item.parse_id, ordinal: item.ordinal, kind: item.kind, text: item.text,
      location: { page: item.locator.page ?? null, headingPath: item.locator.section_path ?? [],
        paragraph: item.locator.paragraph ?? null, lineStart: item.locator.line_start ?? null,
        lineEnd: item.locator.line_end ?? null, charStart: item.locator.char_start ?? null,
        charEnd: item.locator.char_end ?? null, blockIndex: item.locator.block_index ?? null },
    })) }
}

export async function readCourseRole() {
  return data(await getCourseProfile({ client: apiClient })).role ?? null
}
export async function saveCourseRole(role: 'teacher' | 'student', guideDismissed = false) {
  return data(await updateCourseProfile({ client: apiClient, body: { role, guide_dismissed: guideDismissed }, headers: headers() })).role ?? role
}
export async function retryCourseDocument(id: string, documentId: string) {
  return document(data(await organizeSharedDocument({ client: apiClient,
    path: { kb_id: id, document_id: documentId }, headers: headers() })))
}

export async function readCourseProfile() {
  const value = data(await getCourseProfile({ client: apiClient }))
  return { role: value.role ?? null, guideDismissed: value.guide_dismissed ?? false }
}
