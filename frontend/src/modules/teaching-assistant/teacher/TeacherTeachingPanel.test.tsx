import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { TeacherTeachingPanel } from './TeacherTeachingPanel'
import * as api from '../teachingApi'

vi.mock('../teachingApi', () => ({
  getTeachingSettings: vi.fn(), listTeachingActivities: vi.fn(), getLearningSummary: vi.fn(),
  createTeachingActivity: vi.fn(), updateTeachingSettings: vi.fn(), getTeachingActivity: vi.fn(),
  updateTeachingActivity: vi.fn(), getTeachingSource: vi.fn(), runTeachingActivity: vi.fn(), publishTeachingActivity: vi.fn(),
}))
vi.mock('../../research-materials', async (original) => ({
  ...await original<object>(), listAgentMaterials: vi.fn().mockResolvedValue([]),
}))
afterEach(cleanup)
const rubric = [{ id: 'a', title: '论点', max_score: 30 }, { id: 'b', title: '证据', max_score: 40 }, { id: 'c', title: '结构', max_score: 30 }]
const course = { id: 'course', name: '课堂研究', description: '', access: 'owner' as const, sharingEnabled: true, shareToken: null, readyDocumentCount: 0, documents: [] }
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getTeachingSettings).mockResolvedValue({ course_id: 'course', version: 0, objectives: '', rubric })
  vi.mocked(api.listTeachingActivities).mockResolvedValue([])
  vi.mocked(api.getLearningSummary).mockResolvedValue({ sample_count: 0, issues: [], updated_at: null })
})

test('saves a lesson draft with the selected duration and objectives', async () => {
  render(<TeacherTeachingPanel course={course} />)
  fireEvent.click(await screen.findByRole('button', { name: '新建备课' }))
  fireEvent.change(screen.getByLabelText('教学目标'), { target: { value: '比较沉默的两种解释' } })
  fireEvent.change(screen.getByLabelText('课时（分钟）'), { target: { value: '90' } })
  vi.mocked(api.createTeachingActivity).mockResolvedValue({ id: 'lesson', kind: 'lesson_plan', state: 'draft', version: 1, input: { objectives: '比较沉默的两种解释', duration_minutes: 90 }, shared_with_teacher: false, course_id: 'course', owner_user_id: 'teacher', created_at: '', updated_at: '' })
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))
  await waitFor(() => expect(api.createTeachingActivity).toHaveBeenCalledWith('course', expect.objectContaining({ kind: 'lesson_plan', input: expect.objectContaining({ objectives: '比较沉默的两种解释', duration_minutes: 90 }) }), expect.any(String)))
  expect(await screen.findByText('草稿已保存')).toBeInTheDocument()
})

test('does not expose teacher controls to course readers', () => {
  render(<TeacherTeachingPanel course={{ ...course, access: 'reader' }} />)
  expect(screen.queryByRole('button', { name: '新建备课' })).not.toBeInTheDocument()
  expect(api.getTeachingSettings).not.toHaveBeenCalled()
})

test('course records are organized into lesson and assignment workspaces', async () => {
  const record = { course_id: 'course', owner_user_id: 'teacher', version: 1, shared_with_teacher: false, created_at: '2026-09-12T00:00:00Z', updated_at: '2026-09-12T00:00:00Z', state: 'draft' as const }
  vi.mocked(api.listTeachingActivities).mockResolvedValue([
    { ...record, id: 'lesson', kind: 'lesson_plan', input: { title: '社会观察教案' } },
    { ...record, id: 'assignment', kind: 'assignment_review', input: { title: '调查设计作业' } },
  ])
  render(<TeacherTeachingPanel course={course} />)
  fireEvent.click(await screen.findByRole('button', { name: '教案文稿' }))
  const table = await screen.findByRole('table', { name: '教学记录列表' })
  expect(table).toHaveTextContent('社会观察教案')
  expect(table).not.toHaveTextContent('调查设计作业')
  fireEvent.click(screen.getByRole('button', { name: '作业管理' }))
  expect(screen.getByRole('table', { name: '教学记录列表' })).toHaveTextContent('调查设计作业')
  expect(screen.getByRole('table', { name: '教学记录列表' })).not.toHaveTextContent('社会观察教案')
})
