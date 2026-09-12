import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { CourseCatalog } from './CourseCatalog'
afterEach(cleanup)
test('students can read sample units and self-check without teacher import controls', () => {
  render(<CourseCatalog courses={[]} role="student" query="" onOpen={vi.fn()} onRemove={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: '预览课程 社会调查方法' }))
  expect(screen.getByRole('heading', { name: '社会调查方法' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '使用此课程模板' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '开始第一单元' }))
  expect(screen.getByRole('heading', { name: '从现象提出研究问题' })).toBeInTheDocument()
  fireEvent.change(screen.getByRole('textbox', { name: '我的练习笔记' }), { target: { value: '研究对象为本校大一学生' } })
  fireEvent.click(screen.getByRole('button', { name: '下一单元' }))
  expect(screen.getByRole('heading', { name: '抽样与调查伦理' })).toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: '我的练习笔记' })).toHaveValue('')
})
