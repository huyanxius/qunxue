import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = process.env.QUNXUE_AUDIT_ROOT ?? fileURLToPath(new URL('../../', import.meta.url))
const gate = resolve(root, 'tools/dependency-audit/check.mjs')
// Older revisions have no audit gate. Run the same cases against that baseline.
const evaluate = existsSync(gate)
  ? (await import(pathToFileURL(gate).href)).evaluate
  : () => ({ status: 0, findings: [] })

const today = '2026-11-12'
const primaryId = 'GHSA-2345-2345-2345'
const nestedId = 'GHSA-3456-3456-3456'
const pythonAlias = 'GHSA-4567-4567-4567'
const npmNode = 'node_modules/example-npm'
const nestedNode = 'node_modules/example-parent/node_modules/example-npm'
const parentNode = 'node_modules/example-parent'

function advisory(id, source, range) {
  return { source, name: 'example-npm', dependency: 'example-npm', title: 'Synthetic',
    severity: 'high', url: `https://github.com/advisories/${id}`, range,
    cwe: [], cvss: { score: 0, vectorString: null } }
}

function fixture() {
  const npm = {
    auditReportVersion: 2,
    vulnerabilities: {
      'example-npm': { name: 'example-npm', severity: 'high', isDirect: true,
        via: [advisory(primaryId, 1, '<2.0.0'), advisory(nestedId, 2, '>=2.0.0 <3.0.0')],
        effects: ['example-parent'], range: '<3.0.0', nodes: [npmNode, nestedNode], fixAvailable: true },
      'example-parent': { name: 'example-parent', severity: 'high', isDirect: true, via: ['example-npm'],
        effects: [], range: '1.0.0', nodes: [parentNode], fixAvailable: true },
    },
    metadata: {
      vulnerabilities: { info: 0, low: 0, moderate: 0, high: 2, critical: 0, total: 2 },
      dependencies: { prod: 4, dev: 0, optional: 0, peer: 0, peerOptional: 0, total: 3 },
    },
  }
  const pythonAdvisory = { id: 'PYSEC-2099-1', fix_versions: ['2.0.0'], aliases: [pythonAlias] }
  return {
    today,
    npm: { status: 1, stdout: JSON.stringify(npm) },
    pip: { status: 1, stdout: JSON.stringify({ dependencies: [
      { name: 'example-python', version: '1.0.0', vulns: [pythonAdvisory, pythonAdvisory] },
    ], fixes: [] }) },
    lock: { lockfileVersion: 3, packages: {
      '': { name: 'synthetic-project', version: '1.0.0' },
      [npmNode]: { version: '1.2.0' },
      [nestedNode]: { version: '2.1.0' },
      [parentNode]: { version: '1.0.0' },
    } },
    requirements: ['example-python==1.0.0 \\', '    --hash=sha256:synthetic',
      '    # via', '    #   example-sdk', '    #   qunxue-api', ''].join('\n'),
    exceptions: [],
  }
}

const scoped = [
  { ecosystem: 'npm', package: 'example-npm', version: '1.2.0', advisories: [primaryId] },
  { ecosystem: 'npm', package: 'example-npm', version: '2.1.0', advisories: [nestedId] },
  { ecosystem: 'pypi', package: 'example-python', version: '1.0.0', advisories: [pythonAlias] },
].map((entry) => ({ ...entry, reason: 'Synthetic compatibility follow-up', expires: '2026-11-13' }))

test('blocks all new findings and attributes each to its locked version and path', () => {
  const result = evaluate(fixture())
  assert.equal(result.status, 1)
  assert.deepEqual(result.findings.map(({ id, version, paths, state }) => [id, version, paths, state]), [
    [primaryId, '1.2.0', [npmNode], 'unexcepted'],
    [nestedId, '2.1.0', [nestedNode], 'unexcepted'],
    ['PYSEC-2099-1', '1.0.0', ['example-sdk', 'qunxue-api'], 'unexcepted'],
  ])
})

test('accepts only the matching package version and advisory through its expiry date', () => {
  const input = { ...fixture(), exceptions: scoped }
  const allowed = evaluate(input)
  assert.equal(allowed.status, 0)
  assert.equal(allowed.findings.filter(({ state }) => state === 'excepted').length, 3)

  const wrongVersion = { ...scoped[1], version: '2.0.0' }
  const partial = evaluate({ ...input, exceptions: [scoped[0], wrongVersion, scoped[2]] })
  assert.equal(partial.status, 1)
  assert.deepEqual(partial.findings.filter(({ state }) => state === 'unexcepted').map(({ id }) => id), [nestedId])
})

test('blocks matching exceptions on their expiry date', () => {
  const result = evaluate({ ...fixture(), today: '2026-11-13', exceptions: scoped })
  assert.equal(result.status, 1)
  assert.equal(result.findings.filter(({ state }) => state === 'expired').length, 3)
})

test('identifies scanner errors even when the exit code is also used for findings', () => {
  const input = { ...fixture(), exceptions: scoped }
  assert.throws(() => evaluate({ ...input, npm: {
    status: 1, stdout: '{"error":{"code":"E503"}}', stderr: 'registry unavailable',
  } }), /npm audit.*registry unavailable/)
  assert.throws(() => evaluate({ ...input, npm: {
    status: 0, stdout: '{"auditReportVersion":2,"metadata":{"vulnerabilities":{"total":0}}}',
  } }), /npm audit.*incomplete/)
  assert.throws(() => evaluate({ ...input, pip: {
    status: 1, stdout: '', stderr: 'OSV unavailable',
  } }), /pip-audit.*OSV unavailable/)
  assert.throws(() => evaluate({ ...input, pip: {
    status: 0, stdout: '{"dependencies":[{"name":"example-python","skip_reason":"unavailable"}],"fixes":[]}',
  } }), /pip-audit.*example-python/)
})

test('rejects wildcard exception scopes', () => {
  assert.throws(() => evaluate({ ...fixture(), exceptions: [{ ...scoped[0], advisories: ['*'] }] }), /exception/i)
})
