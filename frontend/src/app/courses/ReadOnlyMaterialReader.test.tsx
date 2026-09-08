import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'
import { ReadOnlyMaterialReader } from './ReadOnlyMaterialReader'
import type { SharedSource } from '../../modules/shared-knowledge'

beforeAll(() => { HTMLElement.prototype.scrollIntoView = vi.fn() })
afterEach(cleanup)
const source: SharedSource = {
  knowledgeBaseId: 'course-1', knowledgeBaseName: '调查方法',
  document: { id: 'doc-1', filename: '课件.txt', mediaType: 'text/plain', sizeBytes: 1000, parseId: 'parse-1', status: 'ready', knowledgeStatus: 'ready', indexStatus: 'ready', knowledgeError: null, indexError: null, errorMessage: null, warnings: [], createdAt: '2026-09-08', knowledge: { summary: '课堂材料', topics: [{ title: '访谈方法', summary: '围绕访谈组织材料', segmentIds: ['s29'] }], relations: [] } },
  segments: Array.from({ length: 30 }, (_, index) => ({ id: `s${index}`, parseId: 'parse-1', ordinal: index, kind: index === 29 ? 'heading' : 'paragraph', text: `课堂原文 ${index}`, location: { page: null, headingPath: index === 29 ? ['最后一章'] : [], paragraph: index + 1, lineStart: null, lineEnd: null, charStart: null, charEnd: null, blockIndex: null } })),
}
it('keeps professional pagination and opens an anchored segment on its own page', () => {
  render(<ReadOnlyMaterialReader source={source} selectedSegmentId="s29" onBack={() => {}} />)
  expect(screen.getByText('第 2 / 2 页')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '课堂原文 29' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '上一页' }))
  expect(screen.getByText('课堂原文 0')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '新建编码' })).not.toBeInTheDocument()
})
it('locates knowledge in the original document while retaining a mounted Agent panel', () => {
  render(<ReadOnlyMaterialReader source={source} onBack={() => {}} agentPanel={<textarea aria-label="学习草稿" />} />)
  fireEvent.click(screen.getByRole('tab', { name: 'Agent' }))
  fireEvent.change(screen.getByRole('textbox', { name: '学习草稿' }), { target: { value: '问题草稿' } })
  fireEvent.click(screen.getByRole('tab', { name: '知识点' }))
  fireEvent.click(screen.getByRole('button', { name: '访谈方法' }))
  expect(screen.getByText('第 2 / 2 页')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: 'Agent' }))
  expect(screen.getByRole('textbox', { name: '学习草稿' })).toHaveValue('问题草稿')
})
