import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  deleteResearchMaterial,
  getResearchMaterial,
  getResearchMaterialSegment,
  listResearchMaterials,
  reparseResearchMaterial,
  uploadResearchMaterial,
  ResearchMaterialsApiError,
} from './researchMaterialsApi'

afterEach(() => vi.unstubAllGlobals())

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function requestOf(input: RequestInfo | URL, init?: RequestInit): Request {
  return input instanceof Request ? input : new Request(String(input), init)
}

describe('research materials API boundary', () => {
  it('lists materials within the requested research task', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ task_id: 'task-1', items: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await listResearchMaterials('task-1')

    expect(fetchMock).toHaveBeenCalledOnce()
    const [input, init] = fetchMock.mock.calls[0]
    const request = requestOf(input, init)
    expect(new URL(request.url).pathname).toBe('/api/research-tasks/task-1/materials')
    expect(request.credentials).toBe('include')
  })

  it('uploads a supported file as multipart data with its research kind', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({
      material_id: 'material-1', task_id: 'task-1', filename: '访谈.docx',
      media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      size_bytes: 8, status: 'processing', version: 1, parse_version: null,
      segment_count: 0, updated_at: '2026-08-29T00:00:00Z', error_code: null,
    }, 201))
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['content'], '访谈.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })

    const material = await uploadResearchMaterial('task-1', file, 'interview_transcript')

    expect(material.materialId).toBe('material-1')
    const [input, init] = fetchMock.mock.calls[0]
    const request = requestOf(input, init)
    expect(request.method).toBe('POST')
    expect(request.headers.get('Idempotency-Key')).toEqual(expect.any(String))
    expect(request.headers.get('Content-Type')).toMatch(/^multipart\/form-data; boundary=/)
    const form = await request.clone().formData()
    const uploadedFile = form.get('file')
    expect(uploadedFile).not.toBeNull()
    expect(uploadedFile).toMatchObject({ type: file.type })
    expect(form.get('material_kind')).toBe('interview_transcript')
  })

  it('keeps detail, exact segment, reparse and delete under the same task path', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const url = new URL(request.url)
      if (url.pathname.endsWith('/segments/segment-1')) return response({ segment_id: 'segment-1', material_id: 'material-1', parse_id: 'parse-1', ordinal: 0, kind: 'paragraph', text: '原文', locator: { page: 4 } })
      if (url.pathname.endsWith('/reparse')) return response({ material_id: 'material-1', task_id: 'task-1', filename: '论文.pdf', media_type: 'application/pdf', size_bytes: 10, status: 'processing', version: 2, parse_version: null, segment_count: 0, updated_at: '2026-08-29T00:00:00Z', error_code: null })
      if (request.method === 'DELETE') return new Response(null, { status: 204 })
      return response({ material_id: 'material-1', task_id: 'task-1', filename: '论文.pdf', media_type: 'application/pdf', size_bytes: 10, status: 'ready', version: 1, parse_version: 1, segment_count: 2, updated_at: '2026-08-29T00:00:00Z', error_code: null, segments: [] })
    })
    vi.stubGlobal('fetch', fetchMock)

    await getResearchMaterial('task-1', 'material-1')
    await getResearchMaterialSegment('task-1', 'material-1', 'segment-1')
    await reparseResearchMaterial('task-1', 'material-1')
    await deleteResearchMaterial('task-1', 'material-1')

    const paths = fetchMock.mock.calls.map(([input, init]) => new URL(requestOf(input, init).url).pathname)
    expect(paths).toEqual([
      '/api/research-tasks/task-1/materials/material-1',
      '/api/research-tasks/task-1/materials/material-1/segments/segment-1',
      '/api/research-tasks/task-1/materials/material-1/reparse',
      '/api/research-tasks/task-1/materials/material-1',
    ])
    expect(requestOf(fetchMock.mock.calls[2][0], fetchMock.mock.calls[2][1]).method).toBe('POST')
    expect(requestOf(fetchMock.mock.calls[3][0], fetchMock.mock.calls[3][1]).method).toBe('DELETE')
  })

  it('passes a historical parse id when opening a persisted citation', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({
      segment_id: 'segment-old', material_id: 'material-1', parse_id: 'parse-old',
      ordinal: 0, kind: 'paragraph', text: '旧版本原文', locator: { paragraph: 1 },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await getResearchMaterialSegment(
      'task-1',
      'material-1',
      'segment-old',
      undefined,
      'parse-old',
    )

    const [input, init] = fetchMock.mock.calls[0]
    const request = requestOf(input, init)
    expect(new URL(request.url).searchParams.get('parse_id')).toBe('parse-old')
  })

  it('preserves generated API status and error details for callers', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      error: { code: 'research_material_not_found', message: '研究材料不存在。', trace_id: 'trace-1' },
    }, 404)))

    await expect(getResearchMaterial('task-1', 'material-1')).rejects.toEqual(
      expect.objectContaining({
        name: 'ResearchMaterialsApiError',
        message: '研究材料不存在。',
        status: 404,
      } satisfies Partial<ResearchMaterialsApiError>),
    )
  })

  it('keeps AbortError semantics when a caller cancels a request', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new DOMException('The operation was aborted.', 'AbortError')
    }))

    await expect(listResearchMaterials('task-1')).rejects.toMatchObject({ name: 'AbortError' })
  })
})
