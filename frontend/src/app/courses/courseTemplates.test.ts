import { beforeEach, expect, test, vi } from 'vitest'
import { createCourse, uploadCourseDocument } from '../../modules/shared-knowledge'
import { courseTemplates, importCourseTemplate, type TemplateImportProgress } from './courseTemplates'
vi.mock('../../modules/teaching-assistant', () => ({ getTeachingSettings: vi.fn(async () => ({ version: 0, rubric: [] })), updateTeachingSettings: vi.fn(async () => ({})) }))
vi.mock('../../modules/shared-knowledge', () => ({ createCourse: vi.fn(), uploadCourseDocument: vi.fn() }))
beforeEach(() => vi.clearAllMocks())
test('resumes a partial template import without recreating the course or uploaded units', async () => {
  vi.mocked(createCourse).mockResolvedValue({ id: 'new-course' } as Awaited<ReturnType<typeof createCourse>>)
  vi.mocked(uploadCourseDocument).mockResolvedValueOnce({ id: 'first' } as Awaited<ReturnType<typeof uploadCourseDocument>>).mockRejectedValueOnce(new Error('上传失败'))
  let progress: TemplateImportProgress = { courseId: null, uploaded: 0 }
  await expect(importCourseTemplate(courseTemplates[0], progress, (next) => { progress = next })).rejects.toThrow('上传失败')
  expect(progress).toEqual({ courseId: 'new-course', uploaded: 1, configured: true })
  vi.mocked(uploadCourseDocument).mockResolvedValue({ id: 'uploaded' } as Awaited<ReturnType<typeof uploadCourseDocument>>)
  expect(await importCourseTemplate(courseTemplates[0], progress, (next) => { progress = next })).toBe('new-course')
  expect(createCourse).toHaveBeenCalledTimes(1)
  expect(uploadCourseDocument).toHaveBeenNthCalledWith(3, 'new-course', expect.objectContaining({ name: '02-抽样与调查伦理.md' }))
  expect(progress.uploaded).toBe(4)
})
