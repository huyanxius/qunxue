import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  getProfessionalMaterialArchive,
  updateProfessionalMaterialProfile,
  uploadMaterialBatch,
} from './professionalMaterialsApi'

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

describe('professional material archive API boundary', () => {
  it('loads the task archive and updates only the selected durable material', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      if (request.method === 'PATCH') return response({ material_id: 'material-1' })
      return response({
        task_id: 'task-1', profiles: [], batches: [], collections: [], literature: [],
        cases: [], relations: [], duplicate_hints: [],
        inventory: {
          catalog_pending_material_ids: [], parse_failed_material_ids: [],
          suspected_duplicate_literature_ids: [], pending_deidentification_material_ids: [],
          restricted_material_ids: [],
        },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    await getProfessionalMaterialArchive('task-1')
    await updateProfessionalMaterialProfile('task-1', 'material-1', {
      research_role: 'empirical_material', specific_type: 'interview', stage: 'collection',
      batch_id: null, tags: [], collection_ids: [], sensitivity: 'sensitive',
      consent_scope: 'project_only', deidentification_status: 'complete',
      model_processing_scope: 'external_allowed',
    })

    const requests = fetchMock.mock.calls.map(([input, init]) => requestOf(input, init))
    expect(requests.map((request) => new URL(request.url).pathname)).toEqual([
      '/api/research-tasks/task-1/material-archive',
      '/api/research-tasks/task-1/material-archive/materials/material-1',
    ])
    expect(requests[1].method).toBe('PATCH')
    expect(requests[1].headers.get('Idempotency-Key')).toEqual(expect.any(String))
  })

  it('keeps every file result from a 207 batch upload', async () => {
    const fetchMock = vi.fn(async (
      _input: RequestInfo | URL,
      _init?: RequestInit,
    ) => response({
      batch_id: 'batch-1',
      items: [
        { filename: 'a.txt', status: 'created', material_id: 'material-1' },
        { filename: 'b.png', status: 'failed', error_code: 'unsupported_material_format' },
      ],
    }, 207))
    vi.stubGlobal('fetch', fetchMock)

    const result = await uploadMaterialBatch(
      'task-1', 'batch-1', [new File(['a'], 'a.txt')], 'field_note',
    )

    expect(result.items.map((item) => item.status)).toEqual(['created', 'failed'])
    const [input, init] = fetchMock.mock.calls[0]
    const request = requestOf(input, init)
    expect(request.headers.get('Idempotency-Key')).toEqual(expect.any(String))
    expect((await request.clone().formData()).getAll('files')).toHaveLength(1)
  })
})
