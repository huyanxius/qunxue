import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterAll, beforeAll, afterEach, expect, it, vi } from 'vitest'
import { COURSE_INVITATION_KEY } from './CourseInvitationRoute'
import { CoursesPage } from './CoursesPage'

const dialogMethods = Object.getOwnPropertyDescriptors(HTMLDialogElement.prototype)
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open') } })
})
afterAll(() => {
  for (const key of ['showModal', 'close']) {
    if (dialogMethods[key]) Object.defineProperty(HTMLDialogElement.prototype, key, dialogMethods[key])
    else Reflect.deleteProperty(HTMLDialogElement.prototype, key)
  }
})
vi.mock('./CourseShader', () => ({ CourseShader: () => null }))

vi.mock('../../modules/account', () => ({ useAccount: () => ({ sessionState: { status: 'authenticated', session: { user: { displayName: '研究者' } } } }) }))
afterEach(() => { cleanup(); sessionStorage.clear(); vi.unstubAllGlobals() })
const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
const course = { id: 'kb-1', name: '社会调查方法', description: '课堂资料', viewer_access: 'owner', sharing_enabled: false, documents: [], ready_document_count: 0 }

it('teacher can create a course and reach its document management', async () => {
  let saved = false
  vi.stubGlobal('fetch', async (input: Request) => {
    if (input.url.endsWith('/course-profile')) return json({ role: 'teacher' })
    if (input.method === 'POST') { saved = true; return json(course) }
    return json({ items: saved ? [course] : [] })
  })
  render(<MemoryRouter initialEntries={['/courses?view=teacher']}><CoursesPage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: '创建课程' }))
  fireEvent.change(screen.getByLabelText('课程名称'), { target: { value: '社会调查方法' } })
  fireEvent.click(screen.getByRole('button', { name: '保存课程' }))
  expect(await screen.findByRole('heading', { name: '社会调查方法' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '上传资料' })).toBeInTheDocument()
})

it('student can open added course without management controls', async () => {
  vi.stubGlobal('fetch', async (input: Request) => input.url.endsWith('/course-profile') ? json({ role: 'student' }) : json(input.url.endsWith('/kb-1')
    ? { ...course, viewer_access: 'reader', sharing_enabled: true }
    : { items: [{ ...course, viewer_access: 'reader', sharing_enabled: true }] }))
  render(<MemoryRouter initialEntries={['/courses?view=student']}><CoursesPage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: '打开课程 社会调查方法' }))
  expect(await screen.findByRole('link', { name: '开始学习' })).toHaveAttribute('href', '/agent?reference_knowledge_base_id=kb-1')
  expect(screen.queryByRole('button', { name: '上传资料' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '开启分享' })).not.toBeInTheDocument()
})

it('invalid share link reports failure without claiming the source was added', async () => {
  vi.stubGlobal('fetch', async (input: Request) => input.url.endsWith('/course-profile') ? json({ role: 'student' }) : input.method === 'POST'
    ? new Response(JSON.stringify({ error: { message: '链接无效或已关闭。' } }), { status: 404, headers: { 'Content-Type': 'application/json' } })
    : json({ items: [] }))
  sessionStorage.setItem(COURSE_INVITATION_KEY, 'invalid-token-value-12345')
  render(<MemoryRouter initialEntries={['/courses/join']}><CoursesPage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: '添加到我的知识来源' }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('链接无效或已关闭'))
  expect(screen.queryByText('已添加课程')).not.toBeInTheDocument()
})

it('asks for a role once and restores the saved choice without parallel role tabs', async () => {
  let role: string | null = null
  vi.stubGlobal('fetch', async (input: Request) => {
    if (input.url.endsWith('/course-profile')) {
      if (input.method === 'PATCH') role = (await input.json()).role
      return json({ role })
    }
    return json({ items: [] })
  })
  const first = render(<MemoryRouter><CoursesPage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: '开始使用课程' }))
  fireEvent.click(await screen.findByRole('button', { name: /我是学生/ }))
  expect(await screen.findByRole('button', { name: '添加课程' })).toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '教师' })).not.toBeInTheDocument()
  first.unmount()
  render(<MemoryRouter><CoursesPage /></MemoryRouter>)
  expect(await screen.findByRole('button', { name: '添加课程' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /我是学生/ })).not.toBeInTheDocument()
})

it('shows independent processing stages and an entry to the course knowledge library', async () => {
  vi.stubGlobal('fetch', async (input: Request) => {
    if (input.url.endsWith('/course-profile')) return json({ role: 'teacher' })
    if (input.url.endsWith('/kb-1')) return json({ ...course, documents: [{
      id: 'd1', filename: '课件.pptx', media_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      size_bytes: 100, parse_id: 'p1', status: 'ready', created_at: '2026-09-08',
      knowledge_status: 'running', index_status: 'failed', index_error: '语义索引暂不可用',
    }] })
    return json({ items: [course] })
  })
  render(<MemoryRouter initialEntries={['/courses?kb_id=kb-1']}><CoursesPage /></MemoryRouter>)
  expect(await screen.findByText('知识整理中')).toBeInTheDocument()
  expect(screen.getByText('语义索引失败')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '浏览课程知识库' })).toHaveAttribute('href', '/knowledge?scope=courses&kb_id=kb-1')
  expect(screen.getByRole('button', { name: '重试处理 课件.pptx' })).toBeInTheDocument()
})

it('introduces courses before role choice and gives the selected role a first action', async () => {
  let role: string | null = null
  vi.stubGlobal('fetch', async (input: Request) => {
    if (input.url.endsWith('/course-profile')) {
      if (input.method === 'PATCH') role = (await input.json()).role
      return json({ role, guide_dismissed: false })
    }
    return json({ items: [] })
  })
  render(<MemoryRouter initialEntries={['/courses']}><CoursesPage /></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: '课件、知识点和学习对话，在同一门课程里' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /我是教师/ })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '开始使用课程' }))
  fireEvent.click(await screen.findByRole('button', { name: /我是教师/ }))
  expect(await screen.findByRole('heading', { name: '先创建你的第一门课程' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '创建第一门课程' }))
  expect(screen.getByLabelText('课程名称')).toBeInTheDocument()
})

it('requires explicit course deletion and lets the teacher cancel', async () => {
  const deleted = vi.fn()
  vi.stubGlobal('fetch', async (input: Request) => {
    if (input.url.endsWith('/course-profile')) return json({ role: 'teacher', guide_dismissed: true })
    if (input.method === 'DELETE') { deleted(); return new Response(null, { status: 204 }) }
    return json(input.url.endsWith('/kb-1') ? course : { items: [course] })
  })
  render(<MemoryRouter initialEntries={['/courses?kb_id=kb-1']}><CoursesPage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: '删除课程' }))
  expect(await screen.findByRole('dialog', { name: '删除课程？' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '保留课程' }))
  expect(deleted).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '删除课程' }))
  fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
  await waitFor(() => expect(deleted).toHaveBeenCalledTimes(1))
})

it('finishes the remaining uploads and reports a failed file without losing the batch', async () => {
  let uploads = 0
  vi.stubGlobal('fetch', async (input: Request) => {
    if (input.url.endsWith('/course-profile')) return json({ role: 'teacher', guide_dismissed: true })
    if (input.method === 'POST') {
      uploads++
      if (uploads === 1) throw new TypeError('network unavailable')
      return json({ id: 'doc-2', filename: 'second.txt', status: 'ready', size_bytes: 6 })
    }
    return json(input.url.endsWith('/kb-1') ? course : { items: [course] })
  })
  const { container } = render(<MemoryRouter initialEntries={['/courses?kb_id=kb-1']}><CoursesPage /></MemoryRouter>)
  await screen.findByRole('button', { name: '上传资料' })
  fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [new File(['first'], 'first.txt'), new File(['second'], 'second.txt')] } })
  await waitFor(() => expect(uploads).toBe(2))
  expect(await screen.findByRole('status')).toHaveTextContent('1 份资料上传或解析失败')
})
