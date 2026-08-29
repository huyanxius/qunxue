import { afterEach, describe, expect, it, vi } from 'vitest'

import type {
  CreateAnalysisAnnotationInput,
  CreateAnalysisCodeInput,
  CreateAnalysisMemoInput,
  ResearchAnalysisSnapshot,
} from './researchAnalysisModel'
import {
  createAnalysisAnnotation,
  createAnalysisCode,
  createAnalysisMemo,
  decideAnalysisCode,
  decideAnalysisMemo,
  getAnalysisSnapshot,
} from './researchAnalysisApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function requestOf(input: RequestInfo | URL, init?: RequestInit): Request {
  return input instanceof Request ? input : new Request(String(input), init)
}

const snapshot: ResearchAnalysisSnapshot = {
  task_id: 'task-1',
  annotations: [],
  codes: [],
  memos: [],
  comparisons: [],
}

describe('research analysis generated-client boundary', () => {
  it('loads the task analysis snapshot through the generated operation', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => json(snapshot))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getAnalysisSnapshot('task-1')).resolves.toEqual(snapshot)
    const request = requestOf(...fetchMock.mock.calls[0])
    expect(request.method).toBe('GET')
    expect(new URL(request.url).pathname).toBe('/api/research-tasks/task-1/analysis')
  })

  it('saves exact annotation offsets and keeps description and reflection separate', async () => {
    const payload: CreateAnalysisAnnotationInput = {
      material_id: 'material-1',
      parse_id: 'parse-1',
      segment_id: 'segment-1',
      quote_start: 1,
      quote_end: 3,
      annotation_kind: 'descriptive',
      note: '照护责任集中到姐姐',
      reflection: '需要避免把性别分工当作先验解释',
      case_label: '家庭 A',
      observed_at: '迁移后',
    }
    const created = {
      annotation_id: 'annotation-1', task_id: 'task-1', ...payload,
      quote: '😀乙', quote_hash: 'a'.repeat(64), segment_content_hash: 'b'.repeat(64),
      locator: { page: 4, section_path: [], paragraph: 12, line_start: null, line_end: null, char_start: null, char_end: null, block_index: null },
      created_at: '2026-08-30T00:00:00Z',
    }
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => json(created, 201))
    vi.stubGlobal('fetch', fetchMock)

    await expect(createAnalysisAnnotation('task-1', payload)).resolves.toEqual(created)
    const request = requestOf(...fetchMock.mock.calls[0])
    expect(request.method).toBe('POST')
    expect(request.headers.get('Idempotency-Key')).toMatch(/^research-analysis:/)
    expect(await request.json()).toEqual(payload)
  })

  it('creates user-authored codes and memos through generated operations', async () => {
    const code: CreateAnalysisCodeInput = {
      label: '照护责任重组',
      definition: '迁移后责任重新分配',
      annotation_ids: ['annotation-1'],
      rationale: '研究者核对原文后建立',
    }
    const memo: CreateAnalysisMemoInput = {
      title: '竞争解释',
      content: '经济资源差异也可能解释责任安排',
      memo_kind: 'analytic',
      annotation_ids: ['annotation-1'],
      code_ids: ['code-1'],
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      return new URL(request.url).pathname.endsWith('/codes')
        ? json({ code_id: 'code-1', ...code }, 201)
        : json({ memo_id: 'memo-1', ...memo }, 201)
    })
    vi.stubGlobal('fetch', fetchMock)

    await createAnalysisCode('task-1', code)
    await createAnalysisMemo('task-1', memo)
    const codeRequest = requestOf(...fetchMock.mock.calls[0])
    const memoRequest = requestOf(...fetchMock.mock.calls[1])
    expect(codeRequest.headers.get('Idempotency-Key')).toMatch(/^research-analysis:/)
    expect(memoRequest.headers.get('Idempotency-Key')).toMatch(/^research-analysis:/)
    expect(codeRequest.headers.get('Idempotency-Key')).not.toBe(memoRequest.headers.get('Idempotency-Key'))
    expect(await codeRequest.json()).toEqual(code)
    expect(await memoRequest.json()).toEqual(memo)
  })

  it('sends user candidate decisions with the visible CAS version and reason', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      return json({ id: new URL(request.url).pathname }, 200)
    })
    vi.stubGlobal('fetch', fetchMock)

    await decideAnalysisCode('task-1', 'code-1', { decision: 'confirmed', expected_version: 2, reason: '已核对原文' })
    await decideAnalysisMemo('task-1', 'memo-1', { decision: 'rejected', expected_version: 4, reason: '过度概括' })
    const codeRequest = requestOf(...fetchMock.mock.calls[0])
    const memoRequest = requestOf(...fetchMock.mock.calls[1])
    expect(new URL(codeRequest.url).pathname).toContain('/codes/code-1/decision')
    expect(await codeRequest.json()).toEqual({ decision: 'confirmed', expected_version: 2, reason: '已核对原文' })
    expect(new URL(memoRequest.url).pathname).toContain('/memos/memo-1/decision')
    expect(await memoRequest.json()).toEqual({ decision: 'rejected', expected_version: 4, reason: '过度概括' })
  })
})
