import { apiClient } from '../../api/client'
import * as api from '../../api/generated'

export type {
  TeachingActivity, TeachingInput, TeachingResult, TeachingSource, TeachingSettings,
  TeachingScore, TeachingCitation, RubricDimension, TeachingAnswer, TeachingQuestion,
  LearningSummary, CreateTeachingActivity, UpdateTeachingActivity,
} from '../../api/generated'

function unwrap<T>(result: { data?: T; error?: unknown }): T {
  if (result.error || result.data === undefined) {
    const error = result.error as { error?: { message?: string } } | undefined
    throw new Error(error?.error?.message ?? '教学记录暂时无法读取，请重试。')
  }
  return result.data
}
const headers = (key?: string) => ({ 'Idempotency-Key': key ?? crypto.randomUUID() })
export async function getTeachingSettings(courseId: string) {
  return unwrap(await api.getTeachingSettings({ client: apiClient, path: { kb_id: courseId } }))
}
export async function updateTeachingSettings(courseId: string, body: api.UpdateTeachingSettings, key?: string) {
  return unwrap(await api.updateTeachingSettings({ client: apiClient, path: { kb_id: courseId }, body, headers: headers(key) }))
}
export async function listTeachingActivities(courseId: string) {
  return unwrap(await api.listTeachingActivities({ client: apiClient, path: { kb_id: courseId } })).items
}
export async function createTeachingActivity(courseId: string, body: api.CreateTeachingActivity, key?: string) {
  return unwrap(await api.createTeachingActivity({ client: apiClient, path: { kb_id: courseId }, body, headers: headers(key) }))
}
export async function getTeachingActivity(id: string) {
  return unwrap(await api.getTeachingActivity({ client: apiClient, path: { activity_id: id } }))
}
export async function updateTeachingActivity(id: string, body: api.UpdateTeachingActivity, key?: string) {
  return unwrap(await api.updateTeachingActivity({ client: apiClient, path: { activity_id: id }, body, headers: headers(key) }))
}
export async function getTeachingSource(id: string) {
  return unwrap(await api.getTeachingSource({ client: apiClient, path: { activity_id: id } }))
}
export async function runTeachingActivity(id: string, body: api.TeachingVersion, key?: string) {
  return unwrap(await api.runTeachingActivity({ client: apiClient, path: { activity_id: id }, body, headers: headers(key) }))
}
export async function publishTeachingActivity(id: string, body: api.TeachingVersion, key?: string) {
  return unwrap(await api.publishTeachingActivity({ client: apiClient, path: { activity_id: id }, body, headers: headers(key) }))
}
export async function getLearningSummary(courseId: string) {
  return unwrap(await api.getLearningSummary({ client: apiClient, path: { kb_id: courseId } }))
}
