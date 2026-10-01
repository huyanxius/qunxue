import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
const controls = readFileSync(resolve('src/styles/selection-controls.css'), 'utf8')
const frontier = readFileSync(resolve('src/modules/frontier/frontier.css'), 'utf8')
import { describe, expect, it } from 'vitest'
describe('shared selection control', () => {
  it('uses shared typography, dimensions, color and radius tokens', () => {
    for (const token of ['--qx-control-height', '--qx-radius-control', '--qx-radius-compact', '--qx-text-control', '--qx-font-ui', '--qx-color-accent-soft']) expect(controls).toContain(`var(${token})`)
    expect(controls).not.toMatch(/#[a-f0-9]{3,8}/i)
    expect(controls).not.toMatch(/border-radius:\s*\d|font-size:\s*\d/)
  })
  it('does not implement selected controls as underlines', () => {
    expect(controls).not.toMatch(/border-bottom|inset\s+0\s+-/)
    expect(frontier).not.toContain('.frontier-panel-tabs')
    expect(frontier).not.toContain('.frontier-kinds')
  })
})
