import { createElement } from 'react'
import { act, cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { KnowledgeLibraryShader } from './KnowledgeLibraryShader'

vi.mock('@paper-design/shaders-react', () => {
  const Shader = ({ colors }: { colors: string[] }) => createElement('div', { 'data-testid': 'shader', 'data-colors': JSON.stringify(colors) })
  return { MeshGradient: Shader, Warp: Shader }
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('keeps the background mounted and updates its palette with system appearance', () => {
  let dark = false
  const subscribers = new Set<() => void>()
  vi.stubGlobal('WebGL2RenderingContext', class {})
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() { return query === '(prefers-color-scheme: dark)' && dark },
    addEventListener: (_: string, fn: () => void) => subscribers.add(fn),
    removeEventListener: (_: string, fn: () => void) => subscribers.delete(fn),
  }))
  const screen = render(createElement(KnowledgeLibraryShader))
  const shader = screen.getByTestId('shader')
  const light = shader.getAttribute('data-colors')
  act(() => { dark = true; subscribers.forEach(fn => fn()) })
  expect(screen.getByTestId('shader')).toBe(shader)
  expect(shader.getAttribute('data-colors')).not.toBe(light)
  act(() => { dark = false; subscribers.forEach(fn => fn()) })
  expect(shader.getAttribute('data-colors')).toBe(light)
})
