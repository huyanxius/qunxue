import assert from 'node:assert/strict'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const checker = new URL('./check-style-tokens.mjs', import.meta.url)

function runChecker(css) {
  const fixtureDir = mkdtempSync(join(tmpdir(), 'qunxue-style-check-'))
  const fixture = join(fixtureDir, 'fixture.css')
  writeFileSync(fixture, css)
  const result = spawnSync(process.execPath, [fileURLToPath(checker), fixture], { encoding: 'utf8' })
  rmSync(fixtureDir, { recursive: true, force: true })
  return result
}

test('accepts structural values expressed through semantic tokens', () => {
  const result = runChecker(`
    .control {
      min-height: var(--spacing-tool-control);
      border-radius: var(--radius-compact);
      font-size: var(--text-meta);
    }
  `)

  assert.equal(result.status, 0, result.stderr)
  assert.match(result.stdout, /Style tokens: ok/)
})

test('rejects new raw structural values without policing page colors', () => {
  const result = runChecker(`
    .control {
      min-height: 1.9rem;
      border-radius: 0.35rem;
      color: #654321;
      font-size: 0.62rem;
    }
  `)

  assert.equal(result.status, 1)
  assert.match(result.stderr, /raw control size/)
  assert.match(result.stderr, /raw radius/)
  assert.match(result.stderr, /raw type size/)
  assert.doesNotMatch(result.stderr, /raw color/)
})

