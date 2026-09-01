import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ExistingResearchEntryPage } from './ExistingResearchEntryPage'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function LocationProbe() {
  const location = useLocation()
  return <output aria-label="当前路径">{location.pathname}{location.search}</output>
}

describe('ExistingResearchEntryPage', () => {
  it('creates one project and uploads every selected initial material into it', async () => {
    const taskId = 'existing-research-task'
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(input, init)
      const url = new URL(request.url)
      if (url.pathname === '/api/research-tasks') {
        return Response.json({
          task_id: taskId,
          entry_type: 'material_input',
          entry_mode: 'existing_research',
          lifecycle_status: 'in_progress',
          project_title: '社区照护田野研究',
          project_stage: '材料整理',
          method_orientation: '质性访谈',
          last_central_tool: 'materials',
          status: 'draft',
          version: 1,
          allowed_actions: ['submit_phenomenon'],
          seed_theory_id: null,
          seed_theory_name: null,
          created_at: '2026-08-31T00:00:00Z',
          updated_at: '2026-08-31T00:00:00Z',
        }, { status: 201 })
      }
      if (url.pathname === `/api/research-tasks/${taskId}/materials`) {
        const form = await request.formData()
        const file = form.get('file') as File
        return Response.json({
          material_id: `material-${file.name}`,
          task_id: taskId,
          filename: file.name,
          media_type: file.type,
          material_kind: 'other',
          size_bytes: file.size,
          status: 'ready',
          version: 1,
          parse_version: 1,
          segment_count: 1,
          created_at: '2026-08-31T00:00:00Z',
          updated_at: '2026-08-31T00:00:00Z',
        }, { status: 201 })
      }
      return Response.json({}, { status: 404 })
    })
    vi.stubGlobal('fetch', fetch)

    render(
      <MemoryRouter initialEntries={['/research/existing']}>
        <ExistingResearchEntryPage />
        <LocationProbe />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByRole('textbox', { name: '项目名称' }), {
      target: { value: '社区照护田野研究' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: '当前阶段' }), {
      target: { value: '材料整理' },
    })
    fireEvent.change(screen.getByLabelText('选择初始材料'), {
      target: {
        files: [
          new File(['访谈 A'], '访谈-A.txt', { type: 'text/plain' }),
          new File(['访谈 B'], '访谈-B.md', { type: 'text/markdown' }),
        ],
      },
    })
    fireEvent.click(screen.getByRole('button', { name: '建立项目并导入材料' }))

    await waitFor(
      () => expect(screen.getByLabelText('当前路径')).toHaveTextContent(
        `/research/${taskId}/workspace/materials`,
      ),
      { timeout: 10_000 },
    )
    const taskRequests = fetch.mock.calls.filter(([input, init]) => {
      const request = input instanceof Request ? input : new Request(input, init)
      return new URL(request.url).pathname === '/api/research-tasks'
    })
    const materialRequests = fetch.mock.calls.filter(([input, init]) => {
      const request = input instanceof Request ? input : new Request(input, init)
      return new URL(request.url).pathname.endsWith('/materials')
    })
    expect(taskRequests).toHaveLength(1)
    expect(materialRequests).toHaveLength(2)
    const taskRequest = taskRequests[0]
    if (!taskRequest) throw new Error('Expected one research-task request.')
    const request = taskRequest[0] instanceof Request
      ? taskRequest[0]
      : new Request(taskRequest[0], taskRequest[1])
    await expect(request.json()).resolves.not.toHaveProperty('method_orientation')
  })
})
