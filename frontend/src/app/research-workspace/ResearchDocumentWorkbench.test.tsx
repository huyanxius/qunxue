import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { ResearchDocumentWorkbench } from './ResearchDocumentWorkbench'

vi.mock('../../api/client', () => ({ apiClient: {} }))

describe('ResearchDocumentWorkbench', () => {
  it('renders a document-first three-column research workspace for a real task', async () => {
    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: '理论判断文档' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '研究章节' })).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: '研究 Agent' })).toBeInTheDocument()
    expect(screen.getByText(/尚未生成可编辑研究文档/)).toBeInTheDocument()
    expect(document.querySelector('.research-document-editor .ProseMirror')).not.toBeInTheDocument()
  })

  it('states the preview boundary when the research agent is not available', async () => {
    render(
      <MemoryRouter initialEntries={['/research/task-1/framework']}>
        <Routes>
          <Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText(/当前 Agent 运行环境未连接/)).toBeInTheDocument()
    expect(screen.getAllByText(/不会把静态示例当作真实研究结果/).length).toBeGreaterThan(0)
  })
})
