import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResearchMaterialsPanel } from './ResearchMaterialsPanel'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function requestOf(input: RequestInfo | URL, init?: RequestInit): Request {
  return input instanceof Request ? input : new Request(String(input), init)
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((nextResolve) => { resolve = nextResolve })
  return { promise, resolve }
}

const material = {
  material_id: 'material-1', task_id: 'task-1', filename: '社区访谈.docx',
  media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  size_bytes: 2048, status: 'ready', version: 1, parse_version: 1,
  segment_count: 3, updated_at: '2026-08-29T00:00:00Z', error_code: null,
}

describe('ResearchMaterialsPanel', () => {
  it('persists a qualitative method choice and refreshes the stable workspace snapshot', async () => {
    const analysisSnapshot = {
      task_id: 'task-1', annotations: [], codes: [], memos: [], comparisons: [],
      method_presets: [
        { method: 'thematic_analysis', label: '主题分析', primary_view: 'themes', matrix_axes: ['个案', '主题'], prompts: '发展共享意义模式。', guardrails: '代码不等于主题。' },
        { method: 'case_study', label: '个案研究', primary_view: 'case_matrix', matrix_axes: ['个案', '分析命题'], prompts: '先做个案内解释。', guardrails: '属性不代替个案解释。' },
      ],
      workspace: {
        schema_version: 'qualitative-workspace-v1', content_hash: 'f'.repeat(64),
        method_preset: { method: 'thematic_analysis', version: 0, updated_at: '1970-01-01T00:00:00Z' },
        codebook_entries: [], memo_links: [], case_profiles: [], formal_themes: [], candidate_themes: [], matrix_cells: [],
      },
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const path = new URL(request.url).pathname
      if (path.endsWith('/analysis/workspace/method') && request.method === 'PUT') {
        return response({ method: 'case_study', version: 1, updated_at: '2026-08-31T00:00:00Z' })
      }
      if (path.endsWith('/analysis')) return response(analysisSnapshot)
      if (path.endsWith('/materials/material-1')) return response({ ...material, segments: [] })
      return response({ task_id: 'task-1', items: [material] })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    fireEvent.click(within(dialog).getByRole('button', { name: /社区访谈\.docx/ }))
    fireEvent.click(await within(dialog).findByRole('button', { name: '分析' }))
    const method = await within(dialog).findByRole('combobox', { name: '方法取向' })
    fireEvent.change(method, { target: { value: 'case_study' } })

    await waitFor(() => expect(fetchMock.mock.calls.some((call) => {
      const request = requestOf(...call)
      return request.method === 'PUT' && new URL(request.url).pathname.endsWith('/analysis/workspace/method')
    })).toBe(true))
    await waitFor(() => expect(fetchMock.mock.calls.filter((call) => new URL(requestOf(...call).url).pathname.endsWith('/analysis'))).toHaveLength(2))
  })

  it('paginates long source text and exposes document search instead of rendering every segment at once', async () => {
    const segments = Array.from({ length: 42 }, (_, index) => ({
      segment_id: `segment-${index + 1}`,
      material_id: 'material-1',
      parse_id: 'parse-1',
      ordinal: index,
      kind: index === 0 ? 'heading' : 'paragraph',
      text: index === 0 ? '一、家庭照护的重新分配' : `第 ${index + 1} 段：研究材料中的连续原文。`,
      locator: { paragraph: index + 1, section_path: index === 0 ? ['一、家庭照护的重新分配'] : [] },
    }))
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(requestOf(input, init).url).pathname
      if (path.endsWith('/materials/material-1')) return response({ ...material, segment_count: segments.length, segments })
      return response({ task_id: 'task-1', items: [material] })
    }))

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    fireEvent.click(within(dialog).getByRole('button', { name: /社区访谈\.docx/ }))

    const reader = await within(dialog).findByRole('region', { name: '文档阅读器' })
    expect(within(reader).getByRole('searchbox', { name: '在材料中查找' })).toBeVisible()
    expect(within(reader).getByRole('navigation', { name: '章节导航' })).toBeVisible()
    expect(within(reader).getByText('第 2 段：研究材料中的连续原文。')).toBeVisible()
    expect(within(reader).queryByText('第 42 段：研究材料中的连续原文。')).not.toBeInTheDocument()
    expect(within(reader).getByRole('button', { name: '下一页' })).toBeVisible()
  })

  it('renders as a persistent workspace without modal semantics', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ task_id: 'task-1', items: [] })))

    render(<ResearchMaterialsPanel taskId="task-1" presentation="workspace" />)

    const workspace = await screen.findByRole('region', { name: '研究材料' })
    expect(workspace).toBeVisible()
    expect(screen.queryByRole('dialog', { name: '研究材料' })).not.toBeInTheDocument()
    expect(within(workspace).queryByRole('button', { name: '关闭研究材料' })).not.toBeInTheDocument()
    expect(within(workspace).getByRole('button', { name: '选择文件' })).toBeVisible()
  })

  it('restores the center mode and exact source location through the workspace adapter', async () => {
    const onWorkspaceLocationChange = vi.fn()
    const segment = {
      segment_id: 'segment-1', material_id: 'material-1', parse_id: 'parse-1', ordinal: 0,
      kind: 'paragraph', text: '受访者描述了工作时间的变化。', locator: { page: 4, paragraph: 12 },
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(requestOf(input, init).url).pathname
      if (path.endsWith('/analysis')) return response({ task_id: 'task-1', annotations: [], codes: [], memos: [], comparisons: [] })
      if (path.endsWith('/materials/material-1/segments/segment-1')) return response(segment)
      if (path.endsWith('/materials/material-1')) return response({ ...material, segments: [segment] })
      return response({ task_id: 'task-1', items: [material] })
    }))

    render(
      <ResearchMaterialsPanel
        taskId="task-1"
        presentation="workspace"
        initialDetailMode="analysis"
        initialMaterialId="material-1"
        initialParseId="parse-1"
        initialSegmentId="segment-1"
        onWorkspaceLocationChange={onWorkspaceLocationChange}
      />,
    )

    const workspace = await screen.findByRole('region', { name: '研究材料' })
    expect(await within(workspace).findByRole('button', { name: '分析', pressed: true })).toBeVisible()
    await waitFor(() => expect(onWorkspaceLocationChange).toHaveBeenLastCalledWith({
      mode: 'analysis',
      materialId: 'material-1',
      parseId: 'parse-1',
      segmentId: 'segment-1',
    }))
  })

  it('does not publish a stale center mode while the workspace route changes', async () => {
    const onWorkspaceLocationChange = vi.fn()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(requestOf(input, init).url).pathname
      if (path.endsWith('/analysis')) {
        return response({ task_id: 'task-1', annotations: [], codes: [], memos: [], comparisons: [] })
      }
      return response({ task_id: 'task-1', items: [] })
    }))

    const view = render(
      <ResearchMaterialsPanel
        taskId="task-1"
        presentation="workspace"
        initialDetailMode="source"
        onWorkspaceLocationChange={onWorkspaceLocationChange}
      />,
    )
    await waitFor(() => expect(onWorkspaceLocationChange).toHaveBeenLastCalledWith({
      mode: 'source',
      materialId: null,
      parseId: null,
      segmentId: null,
    }))
    onWorkspaceLocationChange.mockClear()

    view.rerender(
      <ResearchMaterialsPanel
        taskId="task-1"
        presentation="workspace"
        initialDetailMode="analysis"
        onWorkspaceLocationChange={onWorkspaceLocationChange}
      />,
    )

    await waitFor(() => expect(onWorkspaceLocationChange).toHaveBeenLastCalledWith({
      mode: 'analysis',
      materialId: null,
      parseId: null,
      segmentId: null,
    }))
    expect(onWorkspaceLocationChange).not.toHaveBeenCalledWith(expect.objectContaining({ mode: 'source' }))
  })

  it('opens media materials in the transcript timeline instead of the document reader', async () => {
    const onWorkspaceLocationChange = vi.fn()
    const mediaMaterial = {
      ...material,
      material_id: 'media-1',
      filename: '社区访谈.wav',
      media_type: 'audio/wav',
      status: 'uploaded',
      parse_version: null,
      segment_count: 0,
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(requestOf(input, init).url).pathname
      if (path.endsWith('/materials/media-1/transcription')) {
        return response({
          material_id: 'media-1', status: 'ready', automatic_available: false,
          automatic_provider: null, error_code: null,
          current_version: {
            version_id: 'parse-media-1', material_id: 'media-1', version: 1,
            source: 'imported', provider: null, created_from_version_id: null,
            created_at: '2026-09-01T00:00:00Z', is_current: true,
            segments: [{ segment_id: 'media-segment-1', ordinal: 0, speaker: '主持人', start_ms: 1250, end_ms: 3800, text: '请介绍一下。' }],
          },
          versions: [{
            version_id: 'parse-media-1', material_id: 'media-1', version: 1,
            source: 'imported', provider: null, created_from_version_id: null,
            created_at: '2026-09-01T00:00:00Z', is_current: true,
            segments: [{ segment_id: 'media-segment-1', ordinal: 0, speaker: '主持人', start_ms: 1250, end_ms: 3800, text: '请介绍一下。' }],
          }],
        })
      }
      if (path.endsWith('/materials/media-1')) return response({ ...mediaMaterial, segments: [] })
      return response({ task_id: 'task-1', items: [mediaMaterial] })
    }))

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} onWorkspaceLocationChange={onWorkspaceLocationChange} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })

    expect(await within(dialog).findByRole('region', { name: '媒体转录时间轴' })).toBeVisible()
    expect(within(dialog).getByRole('button', { name: '媒体与转录' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(dialog).queryByRole('region', { name: '文档阅读器' })).not.toBeInTheDocument()
    fireEvent.click(await within(dialog).findByRole('button', { name: /00:01\.250.*主持人/ }))
    await waitFor(() => expect(onWorkspaceLocationChange).toHaveBeenLastCalledWith({
      mode: 'source', materialId: 'media-1', parseId: 'parse-media-1', segmentId: 'media-segment-1',
    }))
  })

  it('shows persisted materials and opens an exact source locator in the detail view', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(requestOf(input, init).url).pathname
      if (path.endsWith('/materials/material-1')) return response({ ...material, segments: [{ segment_id: 'segment-1', material_id: 'material-1', parse_id: 'parse-1', ordinal: 0, kind: 'paragraph', text: '受访者描述了工作时间的变化。', locator: { page: 4, paragraph: 12 } }] })
      return response({ task_id: 'task-1', items: [material] })
    }))

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)

    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    expect(within(dialog).getByText('社区访谈.docx')).toBeVisible()
    fireEvent.click(within(dialog).getByRole('button', { name: /社区访谈\.docx/ }))
    expect(await within(dialog).findByText('受访者描述了工作时间的变化。')).toBeVisible()
    expect(within(dialog).getByText('第 4 页 · 第 12 段')).toBeVisible()
  })

  it('opens one inline annotation draft from an exact single-segment text selection', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(requestOf(input, init).url).pathname
      if (path.endsWith('/materials/material-1')) {
        return response({
          ...material,
          segments: [{
            segment_id: 'segment-1', material_id: 'material-1', parse_id: 'parse-1', ordinal: 0,
            kind: 'paragraph', text: '甲😀乙丙', locator: { page: 4, paragraph: 12 },
          }],
        })
      }
      return response({ task_id: 'task-1', items: [material] })
    }))

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    fireEvent.click(within(dialog).getByRole('button', { name: /社区访谈\.docx/ }))
    const source = await within(dialog).findByText('甲😀乙丙')
    const text = source.firstChild as Text
    const range = document.createRange()
    range.setStart(text, 1)
    range.setEnd(text, 4)
    window.getSelection()?.removeAllRanges()
    window.getSelection()?.addRange(range)
    fireEvent.mouseUp(source)

    const draft = await within(dialog).findByRole('region', { name: '片段标记' })
    expect(within(draft).getByText('😀乙')).toBeVisible()
    expect(within(draft).getByRole('textbox', { name: '材料描述' })).toBeVisible()
    expect(within(draft).getByRole('textbox', { name: '研究者反思' })).toBeVisible()
    expect(within(draft).getByRole('textbox', { name: '案例' })).toBeVisible()
    expect(within(draft).getByRole('textbox', { name: '时间' })).toBeVisible()
  })

  it('drops a previous annotation draft when the next selection crosses source segments', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(requestOf(input, init).url).pathname
      if (path.endsWith('/materials/material-1')) {
        return response({
          ...material,
          segments: [
            { segment_id: 'segment-1', material_id: 'material-1', parse_id: 'parse-1', ordinal: 0, kind: 'paragraph', text: '第一个原文片段', locator: { paragraph: 1 } },
            { segment_id: 'segment-2', material_id: 'material-1', parse_id: 'parse-1', ordinal: 1, kind: 'paragraph', text: '第二个原文片段', locator: { paragraph: 2 } },
          ],
        })
      }
      return response({ task_id: 'task-1', items: [material] })
    }))

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    fireEvent.click(within(dialog).getByRole('button', { name: /社区访谈\.docx/ }))
    const first = await within(dialog).findByText('第一个原文片段')
    const second = within(dialog).getByText('第二个原文片段')
    const firstRange = document.createRange()
    firstRange.setStart(first.firstChild as Text, 0)
    firstRange.setEnd(first.firstChild as Text, 3)
    window.getSelection()?.removeAllRanges()
    window.getSelection()?.addRange(firstRange)
    fireEvent.mouseUp(first)
    expect(await within(dialog).findByRole('region', { name: '片段标记' })).toBeVisible()

    const crossRange = document.createRange()
    crossRange.setStart(first.firstChild as Text, 2)
    crossRange.setEnd(second.firstChild as Text, 2)
    window.getSelection()?.removeAllRanges()
    window.getSelection()?.addRange(crossRange)
    fireEvent.mouseUp(first)

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('一次只能选择一个原文片段')
    expect(within(dialog).queryByRole('region', { name: '片段标记' })).not.toBeInTheDocument()
  })

  it('saves the exact selection with separate description, reflection, case, and time fields', async () => {
    const segment = {
      segment_id: 'segment-1', material_id: 'material-1', parse_id: 'parse-1', ordinal: 0,
      kind: 'paragraph', text: '甲😀乙丙', locator: { page: 4, paragraph: 12 },
    }
    const created = {
      annotation_id: 'annotation-1', task_id: 'task-1', material_id: 'material-1', parse_id: 'parse-1', segment_id: 'segment-1',
      segment_content_hash: 'a'.repeat(64), quote: '😀乙', quote_hash: 'b'.repeat(64), quote_start: 1, quote_end: 3,
      locator: { page: 4, section_path: [], paragraph: 12, line_start: null, line_end: null, char_start: null, char_end: null, block_index: null, block_id: null },
      annotation_kind: 'descriptive', case_label: '家庭 A', observed_at: '迁移后', note: '照护责任发生转移',
      reflection: '我需要检查自己的先验假设', created_at: '2026-08-30T00:00:00Z',
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const path = new URL(request.url).pathname
      if (path.endsWith('/analysis/annotations') && request.method === 'POST') return response(created, 201)
      if (path.endsWith('/analysis')) return response({ task_id: 'task-1', annotations: [], codes: [], memos: [], comparisons: [] })
      if (path.endsWith('/materials/material-1')) return response({ ...material, segments: [segment] })
      return response({ task_id: 'task-1', items: [material] })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    fireEvent.click(within(dialog).getByRole('button', { name: /社区访谈\.docx/ }))
    const source = await within(dialog).findByText('甲😀乙丙')
    const range = document.createRange()
    range.setStart(source.firstChild as Text, 1)
    range.setEnd(source.firstChild as Text, 4)
    window.getSelection()?.removeAllRanges()
    window.getSelection()?.addRange(range)
    fireEvent.mouseUp(source)
    const draft = await within(dialog).findByRole('region', { name: '片段标记' })
    fireEvent.change(within(draft).getByRole('textbox', { name: '材料描述' }), { target: { value: '照护责任发生转移' } })
    fireEvent.change(within(draft).getByRole('textbox', { name: '研究者反思' }), { target: { value: '我需要检查自己的先验假设' } })
    fireEvent.change(within(draft).getByRole('textbox', { name: '案例' }), { target: { value: '家庭 A' } })
    fireEvent.change(within(draft).getByRole('textbox', { name: '时间' }), { target: { value: '迁移后' } })
    fireEvent.click(within(draft).getByRole('button', { name: '保存片段标记' }))

    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => {
      const request = requestOf(input, init)
      return request.method === 'POST' && new URL(request.url).pathname.endsWith('/analysis/annotations')
    })).toBe(true))
    const saveCall = fetchMock.mock.calls.find(([input, init]) => {
      const request = requestOf(input, init)
      return request.method === 'POST' && new URL(request.url).pathname.endsWith('/analysis/annotations')
    })
    expect(await requestOf(...saveCall!).json()).toEqual({
      material_id: 'material-1', parse_id: 'parse-1', segment_id: 'segment-1', quote_start: 1, quote_end: 3,
      annotation_kind: 'descriptive', note: '照护责任发生转移', reflection: '我需要检查自己的先验假设',
      case_label: '家庭 A', observed_at: '迁移后',
    })
    expect(await within(dialog).findByText('片段标记已保存。')).toBeVisible()
  })

  it('persists a user-confirmed case comparison through the analysis boundary', async () => {
    const annotations = [
      {
        annotation_id: 'annotation-a', task_id: 'task-1', material_id: 'material-1', parse_id: 'parse-1', segment_id: 'segment-a',
        segment_content_hash: 'a'.repeat(64), quote: '姐姐承担了大部分照护', quote_hash: 'b'.repeat(64), quote_start: 0, quote_end: 11,
        locator: { page: 4, section_path: [], paragraph: 12, line_start: null, line_end: null, char_start: null, char_end: null, block_index: null },
        annotation_kind: 'descriptive', case_label: '家庭 A', observed_at: '迁移后', note: '责任集中', reflection: null, created_at: '2026-08-30T00:00:00Z',
      },
      {
        annotation_id: 'annotation-b', task_id: 'task-1', material_id: 'material-2', parse_id: 'parse-2', segment_id: 'segment-b',
        segment_content_hash: 'c'.repeat(64), quote: '弟弟与父亲仍在分担照护', quote_hash: 'd'.repeat(64), quote_start: 0, quote_end: 12,
        locator: { page: 7, section_path: [], paragraph: 8, line_start: null, line_end: null, char_start: null, char_end: null, block_index: null },
        annotation_kind: 'descriptive', case_label: '家庭 B', observed_at: '迁移后', note: '多人分担', reflection: null, created_at: '2026-08-30T00:00:00Z',
      },
    ]
    const created = {
      comparison_id: 'comparison-user', task_id: 'task-1', title: '照护责任比较', question: '迁移是否必然导致责任集中？',
      case_labels: ['案例：家庭 A', '案例：家庭 B'], time_labels: [],
      findings: [{ kind: 'support', statement: '家庭 A 的责任集中。', annotation_ids: ['annotation-a'] }],
      competing_explanations: [], evidence_gaps: [], next_steps: [], theory_implication: '需要加入家庭资源条件。',
      source: 'user', status: 'confirmed', version: 2, created_at: '2026-08-30T00:00:00Z', decided_at: '2026-08-30T00:00:01Z', decision_reason: '用户创建并确认',
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const path = new URL(request.url).pathname
      if (path.endsWith('/analysis/comparisons') && request.method === 'POST') return response(created, 201)
      if (path.endsWith('/analysis')) return response({ task_id: 'task-1', annotations, codes: [], memos: [], comparisons: [] })
      if (path.endsWith('/materials/material-1')) return response({ ...material, segments: [] })
      return response({ task_id: 'task-1', items: [material] })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    fireEvent.click(within(dialog).getByRole('button', { name: /社区访谈\.docx/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: '分析' }))
    fireEvent.click(await within(dialog).findByRole('button', { name: '建立案例比较' }))
    const form = within(dialog).getByRole('form', { name: '建立案例比较' })
    fireEvent.click(within(form).getByRole('checkbox', { name: '案例：家庭 A' }))
    fireEvent.click(within(form).getByRole('checkbox', { name: '案例：家庭 B' }))
    fireEvent.click(within(form).getByRole('checkbox', { name: /姐姐承担了大部分照护/ }))
    fireEvent.change(within(form).getByRole('textbox', { name: '比较标题' }), { target: { value: created.title } })
    fireEvent.change(within(form).getByRole('textbox', { name: '比较问题' }), { target: { value: created.question } })
    fireEvent.change(within(form).getByRole('textbox', { name: '支持证据' }), { target: { value: created.findings[0].statement } })
    fireEvent.change(within(form).getByRole('textbox', { name: '理论含义' }), { target: { value: created.theory_implication } })
    fireEvent.click(within(form).getByRole('button', { name: '保存案例比较' }))

    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => {
      const request = requestOf(input, init)
      return request.method === 'POST' && new URL(request.url).pathname.endsWith('/analysis/comparisons')
    })).toBe(true))
    expect(await within(dialog).findByRole('article', { name: '已确认案例比较：照护责任比较' })).toBeVisible()
  })

  it('sends a reason and visible version when confirming an Agent comparison', async () => {
    const candidate = {
      comparison_id: 'comparison-agent', task_id: 'task-1', title: '两个家庭的责任重组', question: '家庭资源是否改变迁移影响？',
      case_labels: ['案例：家庭 A', '案例：家庭 B'], time_labels: [],
      findings: [{ kind: 'support', statement: '两个家庭呈现不同变化。', annotation_ids: [] }],
      competing_explanations: ['经济资源差异'], evidence_gaps: ['缺少家庭成员追访'],
      next_steps: [{ kind: 'interview', action: '追访家庭成员', priority: 'high' }], theory_implication: '需加入资源边界。',
      source: 'agent', status: 'candidate', version: 4, created_at: '2026-08-30T00:00:00Z', decided_at: null, decision_reason: null,
    }
    const confirmed = { ...candidate, status: 'confirmed', version: 5, decided_at: '2026-08-30T00:00:01Z', decision_reason: '已核对原文' }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const path = new URL(request.url).pathname
      if (path.endsWith('/analysis/comparisons/comparison-agent/decision') && request.method === 'POST') return response(confirmed)
      if (path.endsWith('/analysis')) return response({ task_id: 'task-1', annotations: [], codes: [], memos: [], comparisons: [candidate] })
      if (path.endsWith('/materials/material-1')) return response({ ...material, segments: [] })
      return response({ task_id: 'task-1', items: [material] })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    fireEvent.click(within(dialog).getByRole('button', { name: /社区访谈\.docx/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: '分析' }))
    const comparison = await within(dialog).findByRole('article', { name: '案例比较候选：两个家庭的责任重组' })
    fireEvent.change(within(comparison).getByRole('textbox', { name: '案例比较判断依据' }), { target: { value: '已核对原文' } })
    fireEvent.click(within(comparison).getByRole('button', { name: '确认案例比较' }))

    await waitFor(async () => {
      const call = fetchMock.mock.calls.find(([input, init]) => new URL(requestOf(input, init).url).pathname.endsWith('/comparison-agent/decision'))
      expect(call).toBeDefined()
      expect(await requestOf(...call!).json()).toEqual({ decision: 'confirmed', reason: '已核对原文', expected_version: 4 })
    })
  })

  it('loads source segments after upload when the upload response only contains a segment count', async () => {
    const uploaded = {
      ...material,
      material_id: 'uploaded-material',
      filename: '观察记录.txt',
      media_type: 'text/plain',
      material_kind: 'observation_record',
    }
    const segment = {
      segment_id: 'uploaded-segment',
      material_id: 'uploaded-material',
      parse_id: 'parse-uploaded',
      ordinal: 0,
      kind: 'paragraph',
      text: '志愿者先听取居民的叙述，再调整服务安排。',
      locator: { line_start: 3, line_end: 4 },
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const path = new URL(request.url).pathname
      if (request.method === 'POST' && path.endsWith('/materials')) return response(uploaded)
      if (path.endsWith('/materials/uploaded-material')) return response({ ...uploaded, segments: [segment] })
      return response({ task_id: 'task-1', items: [] })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)

    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    const input = within(dialog).getByLabelText('选择研究材料文件') as HTMLInputElement
    fireEvent.change(input, {
      target: { files: [new File(['观察记录'], '观察记录.txt', { type: 'text/plain' })] },
    })

    expect(await within(dialog).findByText('志愿者先听取居民的叙述，再调整服务安排。')).toBeVisible()
    expect(fetchMock.mock.calls.some(([input, init]) => {
      const request = requestOf(input, init)
      return request.method === 'GET' && new URL(request.url).pathname.endsWith('/materials/uploaded-material')
    })).toBe(true)
  })

  it('keeps an uploaded material when the initial list response arrives late', async () => {
    const uploaded = {
      ...material,
      material_id: 'uploaded-material',
      filename: '观察记录.txt',
      media_type: 'text/plain',
      material_kind: 'observation_record',
    }
    const listResponse = deferred<Response>()
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const path = new URL(request.url).pathname
      if (request.method === 'POST' && path.endsWith('/materials')) return Promise.resolve(response(uploaded))
      if (path.endsWith('/materials/uploaded-material')) return Promise.resolve(response(uploaded))
      if (path.endsWith('/materials')) return listResponse.promise
      return Promise.resolve(response({}, 404))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    const input = within(dialog).getByLabelText('选择研究材料文件') as HTMLInputElement
    fireEvent.change(input, {
      target: { files: [new File(['观察记录'], '观察记录.txt', { type: 'text/plain' })] },
    })

    expect(await within(dialog).findByRole('button', { name: '查看材料：观察记录.txt' })).toBeVisible()
    listResponse.resolve(response({ task_id: 'task-1', items: [] }))

    await waitFor(() => expect(within(dialog).getByRole('button', { name: /查看材料：观察记录\.txt/ })).toBeVisible())
  })

  it('does not let a slower previous material detail replace the current selection', async () => {
    const first = { ...material, material_id: 'material-first', filename: '第一份访谈.txt', media_type: 'text/plain' }
    const second = { ...material, material_id: 'material-second', filename: '第二份访谈.txt', media_type: 'text/plain' }
    const firstDetail = deferred<Response>()
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const path = new URL(request.url).pathname
      if (path.endsWith('/materials/material-first')) return firstDetail.promise
      if (path.endsWith('/materials/material-second')) {
        return Promise.resolve(response({
          ...second,
          segments: [{ segment_id: 'second-segment', material_id: 'material-second', parse_id: 'parse-2', ordinal: 0, kind: 'paragraph', text: '第二份材料的原文。', locator: { line_start: 2, line_end: 2 } }],
        }))
      }
      return Promise.resolve(response({ task_id: 'task-1', items: [first, second] }))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    await within(dialog).findByText('第一份访谈.txt')
    fireEvent.click(within(dialog).getByRole('button', { name: '查看材料：第一份访谈.txt' }))
    fireEvent.click(within(dialog).getByRole('button', { name: '查看材料：第二份访谈.txt' }))

    expect(await within(dialog).findByText('第二份材料的原文。')).toBeVisible()
    firstDetail.resolve(response({
      ...first,
      segments: [{ segment_id: 'first-segment', material_id: 'material-first', parse_id: 'parse-1', ordinal: 0, kind: 'paragraph', text: '第一份材料的原文。', locator: { line_start: 1, line_end: 1 } }],
    }))

    await waitFor(() => {
      expect(within(dialog).getByText('第二份材料的原文。')).toBeVisible()
      expect(within(dialog).queryByText('第一份材料的原文。')).not.toBeInTheDocument()
    })
  })

  it('opens a historical citation using its parse id for detail and exact segment reads', async () => {
    const legacy = { ...material, material_id: 'material-legacy', filename: '旧版本访谈.txt', media_type: 'text/plain' }
    const legacySegment = {
      segment_id: 'legacy-segment', material_id: 'material-legacy', parse_id: 'parse-old', ordinal: 0,
      kind: 'paragraph', text: '', locator: { line_start: 9, line_end: 9 },
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const url = new URL(request.url)
      if (url.pathname.endsWith('/materials/material-legacy/segments/legacy-segment')) {
        return response({ ...legacySegment, text: '旧版本原文。' })
      }
      if (url.pathname.endsWith('/materials/material-legacy')) {
        return response({ ...legacy, segments: [legacySegment] })
      }
      return response({ task_id: 'task-1', items: [legacy] })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <ResearchMaterialsPanel
        taskId="task-1"
        initialMaterialId="material-legacy"
        initialSegmentId="legacy-segment"
        initialParseId="parse-old"
        onClose={() => undefined}
      />,
    )

    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    expect(await within(dialog).findByText('此片段没有可显示的正文。')).toBeVisible()
    fireEvent.click(within(dialog).getByRole('button', { name: /此片段没有可显示的正文/ }))
    expect(await within(dialog).findByText('旧版本原文。')).toBeVisible()

    const requests = fetchMock.mock.calls.map(([input, init]) => requestOf(input, init))
    const detailRequest = requests.find((request) => {
      const url = new URL(request.url)
      return url.pathname.endsWith('/materials/material-legacy') && url.searchParams.get('parse_id') === 'parse-old'
    })
    const segmentRequest = requests.find((request) => {
      const url = new URL(request.url)
      return url.pathname.endsWith('/segments/legacy-segment') && url.searchParams.get('parse_id') === 'parse-old'
    })
    expect(detailRequest).toBeDefined()
    expect(segmentRequest).toBeDefined()
  })

  it('scrolls a long material to the exact segment referenced by a citation', async () => {
    const targetSegmentId = 'segment-37'
    const segments = Array.from({ length: 45 }, (_, index) => ({
      segment_id: `segment-${index + 1}`,
      material_id: 'material-long',
      parse_id: 'parse-long',
      ordinal: index,
      kind: 'paragraph',
      text: index === 36 ? '需要自动滚动到这里的目标片段。' : `上下文片段 ${index + 1}`,
      locator: { line_start: index + 1, line_end: index + 1 },
    }))
    const longMaterial = {
      ...material,
      material_id: 'material-long',
      filename: '长篇田野笔记.md',
      media_type: 'text/markdown',
      parse_version: 4,
      segment_count: segments.length,
    }
    const scrolledElements: Element[] = []
    const originalScrollIntoView = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollIntoView')
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value(this: Element) {
        scrolledElements.push(this)
      },
    })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(requestOf(input, init).url)
      if (url.pathname.endsWith('/materials/material-long')) return response({ ...longMaterial, segments })
      return response({ task_id: 'task-1', items: [longMaterial] })
    }))

    try {
      render(
        <ResearchMaterialsPanel
          taskId="task-1"
          initialMaterialId="material-long"
          initialSegmentId={targetSegmentId}
          initialParseId="parse-long"
          onClose={() => undefined}
        />,
      )

      const dialog = await screen.findByRole('dialog', { name: '研究材料' })
      const targetText = await within(dialog).findByText('需要自动滚动到这里的目标片段。')
      const targetButton = targetText.closest('button')
      expect(targetButton).not.toBeNull()
      await waitFor(() => expect(scrolledElements).toContain(targetButton))
      expect(targetButton).toHaveAttribute('aria-current', 'location')
    } finally {
      if (originalScrollIntoView) Object.defineProperty(Element.prototype, 'scrollIntoView', originalScrollIntoView)
      else Reflect.deleteProperty(Element.prototype, 'scrollIntoView')
    }
  })

  it('rejects image selection and keeps the upload control constrained to research documents', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ task_id: 'task-1', items: [] }))
    vi.stubGlobal('fetch', fetchMock)
    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    const input = within(dialog).getByLabelText('选择研究材料文件') as HTMLInputElement
    expect(input.accept).toContain('.pdf')
    expect(input.accept).toContain('.docx')
    expect(input.accept).toContain('.md')
    fireEvent.change(input, { target: { files: [new File(['image'], '现场.png', { type: 'image/png' })] } })
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('暂不支持图片')
    expect(fetchMock.mock.calls.every(([input, init]) => requestOf(input, init).method === 'GET')).toBe(true)
  })

  it('retries a failed parse and removes a material after explicit confirmation', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const path = new URL(request.url).pathname
      if (path.endsWith('/materials/material-1/reparse')) return response({ ...material, status: 'processing', version: 2 })
      if (request.method === 'DELETE') return new Response(null, { status: 204 })
      return response({ task_id: 'task-1', items: [{ ...material, status: 'failed', error_code: 'parse_failed' }] })
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('confirm', vi.fn(() => true))
    render(<ResearchMaterialsPanel taskId="task-1" onClose={() => undefined} />)
    const dialog = await screen.findByRole('dialog', { name: '研究材料' })
    fireEvent.click(within(dialog).getByRole('button', { name: '重新解析' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => new URL(requestOf(input, init).url).pathname.endsWith('/reparse'))).toBe(true))
    fireEvent.click(within(dialog).getByRole('button', { name: '删除材料' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => requestOf(input, init).method === 'DELETE')).toBe(true))
  })
})
