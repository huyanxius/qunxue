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
    fireEvent.click(within(dialog).getByRole('button', { name: '查看材料：社区访谈.docx' }))

    const desk = await within(dialog).findByRole('region', { name: '材料阅读台' })
    const reader = within(desk).getByRole('region', { name: '文档阅读器' })
    fireEvent.click(within(desk).getByRole('button', { name: '在材料中查找' }))
    expect(await within(desk).findByRole('searchbox', { name: '在材料中查找' })).toBeVisible()
    expect(within(desk).getByRole('navigation', { name: '章节导航' })).toBeVisible()
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

  it('opens the reading desk on the exact source location carried by the workspace route', async () => {
    const onWorkspaceLocationChange = vi.fn()
    const segment = {
      segment_id: 'segment-1', material_id: 'material-1', parse_id: 'parse-1', ordinal: 0,
      kind: 'paragraph', text: '受访者描述了工作时间的变化。', locator: { page: 4, paragraph: 12 },
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(requestOf(input, init).url).pathname
      if (path.endsWith('/materials/material-1/segments/segment-1')) return response(segment)
      if (path.endsWith('/materials/material-1')) return response({ ...material, segments: [segment] })
      return response({ task_id: 'task-1', items: [material] })
    }))

    render(
      <ResearchMaterialsPanel
        taskId="task-1"
        presentation="workspace"
        initialMaterialId="material-1"
        initialParseId="parse-1"
        initialSegmentId="segment-1"
        onWorkspaceLocationChange={onWorkspaceLocationChange}
      />,
    )

    const workspace = await screen.findByRole('region', { name: '研究材料' })
    const reader = await within(workspace).findByRole('region', { name: '材料阅读台' })
    expect(within(reader).queryByRole('heading', { name: '社区访谈.docx' })).not.toBeInTheDocument()
    expect(within(reader).getByRole('button', { name: '在材料中查找' })).toBeVisible()
    expect(within(reader).getByText('受访者描述了工作时间的变化。')).toBeVisible()
    await waitFor(() => expect(onWorkspaceLocationChange).toHaveBeenLastCalledWith({
      materialId: 'material-1',
      parseId: 'parse-1',
      segmentId: 'segment-1',
    }))
  })

  it('does not publish a location before the material named by the route has loaded', async () => {
    const onWorkspaceLocationChange = vi.fn()
    let releaseDetail: (() => void) | null = null
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(requestOf(input, init).url).pathname
      if (path.endsWith('/materials/material-1')) {
        await new Promise<void>((resolve) => { releaseDetail = resolve })
        return response({ ...material, segments: [] })
      }
      return response({ task_id: 'task-1', items: [material] })
    }))

    render(
      <ResearchMaterialsPanel
        taskId="task-1"
        presentation="workspace"
        initialMaterialId="material-1"
        onWorkspaceLocationChange={onWorkspaceLocationChange}
      />,
    )

    await screen.findByRole('region', { name: '研究材料' })
    // 路由指名了一份材料，它还没读回来之前不能先报一个 materialId: null 的位置——
    // 那会把地址栏改回材料库，等详情到了又跳回来，看起来像界面自己在乱跳。
    expect(onWorkspaceLocationChange).not.toHaveBeenCalledWith(expect.objectContaining({ materialId: null }))
    releaseDetail?.()
    await waitFor(() => expect(onWorkspaceLocationChange).toHaveBeenLastCalledWith({
      materialId: 'material-1',
      parseId: null,
      segmentId: null,
    }))
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
    fireEvent.click(within(dialog).getByRole('button', { name: '查看材料：社区访谈.wav' }))

    expect(await within(dialog).findByRole('region', { name: '媒体转录时间轴' })).toBeVisible()
    expect(within(dialog).queryByRole('region', { name: '文档阅读器' })).not.toBeInTheDocument()
    fireEvent.click(await within(dialog).findByRole('button', { name: /00:01\.250.*主持人/ }))
    await waitFor(() => expect(onWorkspaceLocationChange).toHaveBeenLastCalledWith({
      materialId: 'media-1', parseId: 'parse-media-1', segmentId: 'media-segment-1',
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
    fireEvent.click(within(dialog).getByRole('button', { name: '查看材料：社区访谈.docx' }))
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
    fireEvent.click(within(dialog).getByRole('button', { name: '查看材料：社区访谈.docx' }))
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
    fireEvent.click(within(dialog).getByRole('button', { name: '查看材料：社区访谈.docx' }))
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
    fireEvent.click(within(dialog).getByRole('button', { name: '查看材料：社区访谈.docx' }))
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

  it('stays in the library after upload and carries the fetched source segments into the new row', async () => {
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

    // 上传是材料库这一层的动作，加完仍然停在库里；补详情是为了这一行立刻说得清自己有多少
    // 可引用位置，而不是把人推进一份可能还在解析的文档。
    expect(await within(dialog).findByRole('button', { name: '查看材料：观察记录.txt' })).toBeVisible()
    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => {
      const request = requestOf(input, init)
      return request.method === 'GET' && new URL(request.url).pathname.endsWith('/materials/uploaded-material')
    })).toBe(true))
    fireEvent.click(within(dialog).getByRole('button', { name: '查看材料：观察记录.txt' }))
    expect(await within(dialog).findByText('志愿者先听取居民的叙述，再调整服务安排。')).toBeVisible()
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
    fireEvent.click(await within(dialog).findByRole('button', { name: '材料库' }))
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
    fireEvent.click(within(dialog).getByText('此片段没有可显示的正文。'))
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
      const targetSegment = targetText.closest('.qx-segment')
      expect(targetSegment).not.toBeNull()
      await waitFor(() => expect(scrolledElements).toContain(targetSegment))
      expect(targetSegment).toHaveAttribute('aria-current', 'location')
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
    fireEvent.click(within(dialog).getByRole('button', { name: /^重新解析：/ }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => new URL(requestOf(input, init).url).pathname.endsWith('/reparse'))).toBe(true))
    fireEvent.click(within(dialog).getByRole('button', { name: /^删除材料：/ }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => requestOf(input, init).method === 'DELETE')).toBe(true))
  })
})
