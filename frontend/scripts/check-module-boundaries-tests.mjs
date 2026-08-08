import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'

import { findBoundaryViolations } from './check-module-boundaries.mjs'

const roots = []
after(async () => {
  await Promise.all(roots.map((root) => rm(root, { recursive: true })))
})

const adapters = {
  appApiAdapters: ['api/system.ts'],
  generatedApiAdapters: [
    'api/client.ts',
    'modules/alpha/researchTaskApi.ts',
    // A lookalike .tsx file must not inherit this exact .ts permission.
    'modules/beta/researchTaskApi.ts',
  ],
  httpRuntimeAdapters: ['api/client.ts'],
  moduleApiAdapters: ['modules/alpha/researchTaskApi.ts'],
}

async function check(files, moduleDependencies, policy = adapters) {
  const sourceRoot = await mkdtemp(path.join(tmpdir(), 'qunxue-boundaries-'))
  roots.push(sourceRoot)
  for (const [relative, source] of Object.entries(files)) {
    const target = path.join(sourceRoot, relative)
    await mkdir(path.dirname(target), { recursive: true })
    await writeFile(target, source)
  }
  return findBoundaryViolations({
    sourceRoot,
    policy: { ...policy, moduleDependencies },
  })
}

test('reports the six confirmed boundary rule families', async () => {
  const violations = await check(
    {
      'api/client.ts': `
        import { client } from './generated/client.gen.js'
        export const apiClient = client
        export const request = (input) => globalThis.fetch(input)
      `,
      'api/generated/client.gen.ts': 'export const client = {}',
      'api/generated/index.ts': `
        export interface Dto { readonly task_id: string }
        export const create = () => undefined
        export { privateValue } from '../../modules/alpha/private.js'
      `,
      'api/system.ts': `
        import { create, type Dto } from './generated/index.js'
        export { privateValue } from '../modules/alpha/private.js'
        const firstSystemValue = create
        export const secondSystemValue = firstSystemValue
        type FirstSystemType = Dto
        export type SecondSystemType = FirstSystemType
      `,
      'app/App.tsx': `
        import { privateValue } from '../modules/alpha/private.js'
        import { apiClient } from '../api/client.js'
        export const App = () => [privateValue, apiClient]
      `,
      'modules/alpha/index.ts': `
        import { load } from './researchTaskApi.js'
        export const wrapped = () => load()
        export { secondValue } from './researchTaskApi.js'
        export type { SecondType } from './researchTaskApi.js'
      `,
      'modules/alpha/private.ts': 'export const privateValue = true',
      'modules/alpha/researchTaskApi.ts': `
        import { create, type Dto } from '../../api/generated/index.js'
        const firstValue = create
        const secondValue = firstValue
        type FirstType = Dto
        export type SecondType = FirstType
        export { secondValue }
        export const load = () => create()
      `,
      'modules/alpha/View.tsx': `
        import axios from 'axios'
        import { Link } from 'react-router'
        const model = import('openai')
        window.fetch('/api/research-tasks')
        window.location.href = '/research/next'
        globalThis.history.pushState({}, '', '/research/final')
        export const View = () => [axios, Link, model]
      `,
      'modules/beta/Consumer.ts': `
        import { privateValue } from '../alpha/private.js'
        export type LeakedDto = import('../../api/generated/index.js').Dto
        export { privateValue }
      `,
      'modules/beta/index.ts': 'export const beta = true',
      'modules/beta/researchTaskApi.tsx':
        "import { create } from '../../api/generated/index.js'",
      'modules/delta/index.ts': 'export const delta = true',
      'modules/gamma/View.tsx': 'export const View = () => null',
    },
    { alpha: [], beta: ['alpha'], gamma: [] },
  )

  const expected = [
    'delta is missing an allowed dependency declaration',
    'gamma has no public index.ts',
    'app/App.tsx bypasses alpha/index.ts',
    'app/App.tsx imports API internals instead of an approved app adapter',
    'api/generated/index.ts imports outside the generated API layer',
    'api/system.ts imports product module code from the API layer',
    'api/system.ts re-exports raw generated API value secondSystemValue',
    'api/system.ts re-exports raw generated API type SecondSystemType',
    'modules/beta/Consumer.ts bypasses alpha/index.ts',
    'modules/beta/Consumer.ts imports generated API outside an approved adapter',
    'modules/beta/researchTaskApi.tsx imports generated API outside an approved adapter',
    'modules/alpha/View.tsx imports axios as a direct HTTP client',
    'modules/alpha/View.tsx imports openai as a model SDK',
    'modules/alpha/View.tsx imports routing in a product module',
    'modules/alpha/View.tsx uses HTTP outside the runtime adapter',
    'modules/alpha/View.tsx uses browser routing APIs in a product module',
    'modules/alpha/researchTaskApi.ts re-exports raw generated API value secondValue',
    'modules/alpha/researchTaskApi.ts re-exports raw generated API type SecondType',
    'modules/alpha/index.ts exports module adapter value secondValue',
    'modules/alpha/index.ts exports module adapter type SecondType',
    'modules/alpha/index.ts imports module adapter from its public index',
  ]
  for (const message of expected) {
    assert.ok(violations.includes(message), `${message}\n\n${violations.join('\n')}`)
  }
})

test('allows mapped adapters and ignores comments, strings, URLs, and local names', async () => {
  const violations = await check(
    {
      'api/client.ts': `
        import { client } from './generated/client.gen.js'
        client.setConfig({ fetch: (request) => globalThis.fetch(request) })
        export const apiClient = client
      `,
      'api/generated/client.gen.ts':
        'export const client = { setConfig: (_value) => undefined }',
      'api/generated/index.ts': `
        export interface Dto { readonly task_id: string }
        export const create = () => ({ task_id: 'task-1' })
      `,
      'api/system.ts': 'export const getSystemHealth = () => ({ status: "ok" })',
      'app/App.tsx': `
        import { start } from '../modules/alpha/index.js'
        import { getSystemHealth } from '../api/system.js'
        export const App = () => [start, getSystemHealth]
      `,
      'modules/alpha/index.ts': `
        export { start } from './start.js'
        export type { Task } from './model.js'
      `,
      'modules/alpha/model.ts':
        'export interface Task { readonly taskId: string }',
      'modules/alpha/researchTaskApi.ts': `
        import { apiClient } from '../../api/client.js'
        import { create, type Dto } from '../../api/generated/index.js'
        export function load() {
          const dto: Dto = create()
          return { taskId: dto.task_id, clientReady: Boolean(apiClient) }
        }
      `,
      'modules/alpha/start.ts': `
        import { load } from './researchTaskApi.js'
        export function start() { return load() }
      `,
      'modules/alpha/View.tsx': `
        // window.fetch('/api/research-tasks')
        /* import OpenAI from 'openai' */
        const example = "window.location.href = '/research/example'"
        const url = new URL('/research/task', 'https://example.test')
        const location = { pathname: '/local' }
        const history = { pushState: () => undefined }
        const inspect = (window, document, globalThis) => [
          window.location.pathname,
          document.location.pathname,
          globalThis.history.pushState,
        ]
        history.pushState()
        export const safe = [example, url.pathname, location.pathname, inspect]
      `,
    },
    { alpha: [] },
  )

  assert.deepEqual(violations, [])
})

test('allows a generated-only module adapter without opening other API internals', async () => {
  const policy = {
    appApiAdapters: [],
    generatedApiAdapters: ['modules/graph/knowledgeGraphAdapter.ts'],
    httpRuntimeAdapters: [],
    moduleApiAdapters: [],
  }
  const sharedFiles = {
    'api/generated/index.ts':
      'export interface KnowledgeDto { readonly knowledge_id: string }',
    'modules/graph/index.ts': 'export {}',
    'modules/graph/knowledgeGraphAdapter.ts': `
      import type { KnowledgeDto } from '../../api/generated/index.js'
      export const toId = (entry: KnowledgeDto) => entry.knowledge_id
    `,
  }

  assert.deepEqual(
    await check(sharedFiles, { graph: [] }, policy),
    [],
  )

  const violations = await check(
    {
      ...sharedFiles,
      'api/client.ts': 'export const apiClient = {}',
      'modules/graph/knowledgeGraphAdapter.ts': `
        import type { KnowledgeDto } from '../../api/generated/index.js'
        import { apiClient } from '../../api/client.js'
        export const toId = (entry: KnowledgeDto) => [entry.knowledge_id, apiClient]
      `,
    },
    { graph: [] },
    policy,
  )

  assert.ok(
    violations.includes(
      'modules/graph/knowledgeGraphAdapter.ts imports API internals outside its module adapter',
    ),
    violations.join('\n'),
  )
})
