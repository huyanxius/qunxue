import assert from 'node:assert/strict'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const checker = new URL('./check-style-tokens.mjs', import.meta.url)

function runChecker(...styles) {
  const fixtureDir = mkdtempSync(join(tmpdir(), 'qunxue-style-check-'))
  const fixtures = styles.map((css, index) => {
    const fixture = join(fixtureDir, `fixture-${index}.css`)
    writeFileSync(fixture, css)
    return fixture
  })
  const result = spawnSync(process.execPath, [fileURLToPath(checker), ...fixtures], { encoding: 'utf8' })
  rmSync(fixtureDir, { recursive: true, force: true })
  return result
}

test('accepts structural values expressed through semantic tokens', () => {
  const result = runChecker(`
    :root {
      --spacing-tool-control: 2rem;
      --radius-compact: 4px;
      --text-meta: 0.75rem;
    }
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

test('R03 reports undefined custom properties without a usable fallback', () => {
  const result = runChecker(`
    .workbench {
      background: var(--qx-color-surface-subtle);
      gap: var(--qx-space-5);
      margin: var(--local, var(--missing-backup));
    }
  `)

  assert.deepEqual(
    [...result.stderr.matchAll(/undefined custom property (--[\w-]+)/g)].map((match) => match[1]),
    ['--qx-color-surface-subtle', '--qx-space-5', '--missing-backup'],
  )
  assert.equal(result.status, 1)
})

test('R03 accepts shared declarations, theme overrides and valid fallbacks', () => {
  const result = runChecker(`
    :root { --qx-space-1: 4px; }
    [data-theme='compact'] { --qx-space-1: 2px; }
  `, `
    .workbench {
      gap: var(--qx-space-1);
      margin: var(--local, calc(1px + var(--qx-space-1)));
      content: "var(--example)" var(--optional,);
    }
  `)

  assert.equal(result.status, 0, result.stderr)
})

