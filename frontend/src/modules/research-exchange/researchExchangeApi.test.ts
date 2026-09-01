import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  exportResearchArchive,
  listResearchAuditEvents,
  previewQdpxImport,
} from './researchExchangeApi'

afterEach(() => vi.unstubAllGlobals())

describe('research exchange API', () => {
  it('uses the generated client for audit, archive export, and QDPX preview', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(String(input), init)
      if (request.url.endsWith('/audit')) {
        return Response.json({ task_id: 'task-1', items: [] })
      }
      if (request.url.endsWith('/qdpx-preview')) {
        expect((await request.formData()).get('file')).toBeTruthy()
        return Response.json({
          exchange_id: 'exchange-preview',
          valid: true,
          validation_scope: 'official-xsd',
          specification_version: '1.0',
          project: {
            name: '社区照护田野研究',
            origin: 'QualCoder',
            source_count: 2,
            code_count: 3,
            memo_count: 1,
            case_count: 1,
          },
          restored: false,
        })
      }
      return new Response('archive', {
        headers: {
          'Content-Type': 'application/zip',
          'Content-Disposition': "attachment; filename*=UTF-8''field-study.zip",
          'X-Qunxue-Exchange-Id': 'exchange-export',
          'X-Qunxue-Artifact-SHA256': 'a'.repeat(64),
          'X-Qunxue-Exchange-Loss-Count': '4',
          'X-Qunxue-Exchange-Blocking-Loss-Count': '1',
        },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(listResearchAuditEvents('task-1')).resolves.toEqual([])
    await expect(exportResearchArchive('task-1')).resolves.toMatchObject({
      exchangeId: 'exchange-export',
      filename: 'field-study.zip',
      lossCount: 4,
      blockingLossCount: 1,
    })
    await expect(
      previewQdpxImport('task-1', new File(['qdpx'], 'study.qdpx')),
    ).resolves.toMatchObject({
      exchange_id: 'exchange-preview',
      restored: false,
      project: { name: '社区照护田野研究' },
    })

    const mutationRequests = fetchMock.mock.calls
      .map(([input, init]) => input instanceof Request ? input : new Request(String(input), init))
      .filter((request) => request.method === 'POST')
    expect(mutationRequests).toHaveLength(2)
    for (const request of mutationRequests) {
      expect(request.headers.get('Idempotency-Key')).toMatch(/^research-exchange:/)
    }
  })
})
